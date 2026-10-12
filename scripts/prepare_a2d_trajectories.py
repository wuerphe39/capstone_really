"""Turn A2D's single-action dog videos into three-second box trajectories.

Dog-eating is a specific comparison action, not a generic still label.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from pet_monitor.detection import unique_dog_indices
from pet_monitor.video import dog_class_id
from scripts.prepare_a2d import ROOT, sha256

FRAMES = 15
FPS = 5
def detect_trajectory(path, detector, dog_class, minimum_confidence, imgsz):
    capture = cv2.VideoCapture(str(path))
    fps, total = capture.get(cv2.CAP_PROP_FPS), int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    if not capture.isOpened() or not np.isfinite(fps) or fps <= 0 or total/fps < 3:
        capture.release()
        return None, 'short_or_invalid_video'
    start = max(0, int((total - 3*fps)/2))
    indices = start + np.rint(np.arange(FRAMES)*fps/FPS).astype(int)
    if indices[-1] >= total:
        capture.release()
        return None, 'short_or_invalid_video'
    found = {}
    try:
        for i, index in enumerate(indices):
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, frame = capture.read()
            if not ok:
                return None, 'decode_failure'
            result = detector.predict(frame, classes=[dog_class], conf=min(.1, minimum_confidence),
                                      imgsz=imgsz, verbose=False)[0]
            boxes = result.boxes
            all_confidences = boxes.conf.cpu().numpy()
            all_xyxy = boxes.xyxy.cpu().numpy()
            retained = unique_dog_indices(all_xyxy, all_confidences)
            confidences = all_confidences[retained]
            if int((confidences >= .4).sum()) > 1:
                return None, 'multiple_dogs'
            if not len(retained):
                continue
            order = np.argsort(-confidences)
            best = int(order[0])
            if confidences[best] < minimum_confidence:
                continue
            # YOLO occasionally emits a weak partial duplicate around the
            # same prominent dog. Retain it only with a clear 3x margin;
            # two similarly plausible dogs remain ambiguous.
            if len(order) > 1 and confidences[order[1]] >= confidences[best]/3:
                continue
            x1, y1, x2, y2 = all_xyxy[retained[best]]
            height, width = frame.shape[:2]
            found[i] = ((x1+x2)/(2*width), (y1+y2)/(2*height))
    finally:
        capture.release()
    if len(found) < 9 or min(found) > 1 or max(found) < FRAMES-2:
        return None, 'low_detection_coverage'
    frame_ids = np.array(sorted(found))
    if np.diff(frame_ids).max() > 3:
        return None, 'long_detection_gap'
    coords = np.column_stack([np.interp(np.arange(FRAMES), frame_ids,
                                         [found[i][axis] for i in frame_ids]) for axis in range(2)]).astype(np.float32)
    if not np.isfinite(coords).all() or np.linalg.norm(np.diff(coords, axis=0), axis=1).max() > .15:
        return None, 'invalid_or_jumping_track'
    return coords, None


def run(checkpoint='artifacts/models/yolov8n.pt', minimum_confidence=.15, imgsz=640, stem='short'):
    if not stem.isidentifier() or not (0 < minimum_confidence < 1):
        raise ValueError('invalid dataset stem or detector confidence')
    manifest_path = ROOT / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if sha256(ROOT / 'A2D_main_1_0.tar.bz') != manifest['archive_sha256']:
        raise ValueError('archive differs from selected clip manifest')
    records = manifest['records']
    detector = YOLO(str(checkpoint))
    dog_class = dog_class_id(detector.names)
    arrays, report, exclusions = [], [], []
    for n, row in enumerate(records, 1):
        clip = ROOT / 'selected_clips' / f"{row['id']}.mp4"
        if sha256(clip) != row['sha256']:
            raise ValueError('selected clip differs from manifest')
        coords, reason = detect_trajectory(clip, detector, dog_class, minimum_confidence, imgsz)
        if reason:
            exclusions.append({'id': row['id'], 'action': row['action'], 'split': row['split'], 'reason': reason})
        else:
            arrays.append(coords)
            report.append({'id': row['id'], 'action': row['action'], 'binary_label': 'locomotion' if row['action'] != 'eating' else 'eating',
                           'split': row['split'], 'clip_sha256': row['sha256']})
        if n % 20 == 0 or n == len(records):
            print(f'A2D dog clips {n}/{len(records)} eligible={len(report)}', flush=True)
    if not report:
        raise ValueError('no eligible A2D trajectories')
    # Preserve the publisher test split. Select validation only from quality-
    # eligible train clips, stratified before any classifier is fitted.
    rng = np.random.default_rng(20261011)
    for action in ('eating', 'running', 'walking'):
        candidates = sorted(row['id'] for row in report if row['split'] == 'train' and row['action'] == action)
        if len(candidates) < 3:
            raise ValueError(f'not enough eligible publisher train clips for {action}')
        chosen = set(rng.choice(candidates, size=max(1, round(len(candidates)*.2)), replace=False).tolist())
        for row in report:
            if row['id'] in chosen:
                row['split'] = 'validation'
    output = ROOT / f'{stem}_trajectories.npz'
    np.savez_compressed(output, coords=np.stack(arrays),
                        labels=np.array([int(r['binary_label'] == 'locomotion') for r in report]),
                        splits=np.array([r['split'] for r in report]),
                        ids=np.array([r['id'] for r in report]))
    summary = {'task': 'A2D dog locomotion (walking/running) versus eating, not four-class behavior',
               'source_manifest_sha256': sha256(manifest_path), 'data_sha256': sha256(output),
               'detector_sha256': sha256(Path(checkpoint)), 'detector_confidence': minimum_confidence,
               'detector_imgsz': imgsz,
               'selection': 'single publisher action; decoded three-second clip; contained duplicate boxes suppressed, one dominant dog (>=3x confidence margin over next); >=9/15 detections; <=0.6s gap; no box jump',
               'split': 'publisher test held out; 20% stratified validation from quality-eligible publisher train before classifier fitting',
               'counts': dict(Counter(f"{r['split']}:{r['action']}" for r in report)),
               'exclusions': dict(Counter(row['reason'] for row in exclusions)),
               'exclusion_counts_by_action': dict(Counter(f"{row['action']}:{row['reason']}" for row in exclusions)),
               'records': report}
    (ROOT / f'{stem}_manifest.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps({'eligible': len(report), 'counts': summary['counts'], 'exclusions': summary['exclusions']}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkpoint', default='artifacts/models/yolov8n.pt')
    parser.add_argument('--minimum-confidence', type=float, default=.15)
    parser.add_argument('--imgsz', type=int, default=640)
    parser.add_argument('--stem', default='short')
    args = parser.parse_args()
    run(args.checkpoint, args.minimum_confidence, args.imgsz, args.stem)
