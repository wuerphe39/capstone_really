"""Publisher-labeled locomotion subset, native video timing, frozen v1/v2 models.

This is a COARSE locomotion evaluation, not still/moving/spinning/pacing accuracy.
Unannotated frames are never assigned negative references.
"""
import hashlib
import argparse
import json
import re
import tarfile
from pathlib import Path

import cv2
import numpy as np
import torch
from scipy.io import loadmat
from ultralytics import YOLO

from pet_monitor.lstm import FPS, FRAMES, LABELS, LSTMPredictor, features
from pet_monitor.motion import Observation

ROOT = Path('artifacts/datasets/tigdog')
OUTPUT = Path('artifacts/real_evaluation/tigdog')
LOCOMOTION = {1, 6, 7}  # publisher: walking, walking_backwards, running
LOCAL_ONLY = {2, 4, 9, 10, 11, 13}  # local actions; not a guarantee of fixed image/world position


def frame_reference(labels):
    labels = set(int(item) for item in labels)
    if labels & LOCOMOTION:
        return 'locomotion'
    if labels and labels <= LOCAL_ONLY:
        return 'non_locomotion'
    return None


def coarse_prediction(label):
    return 'non_locomotion' if label == 'still' else 'locomotion' if label in {'moving', 'spinning', 'pacing'} else 'unknown'


def classification_metrics(records, key):
    if not records:
        return {'samples': 0, 'accuracy': None, 'reason': 'no eligible references'}
    labels = ['non_locomotion', 'locomotion']
    matrix = [[sum(r['expected'] == expected and r[key] == predicted for r in records)
               for predicted in labels + ['unknown']] for expected in labels]
    support = {label: sum(r['expected'] == label for r in records) for label in labels}
    accepted = [r for r in records if r[key] != 'unknown']
    f1 = {}
    for label in labels:
        tp = sum(r['expected'] == label and r[key] == label for r in records)
        denominator = support[label]+sum(r[key] == label for r in records)
        f1[label] = 2*tp/denominator if denominator else None
    return {'samples': len(records), 'accuracy': sum(r[key] == r['expected'] for r in records)/len(records),
            'coverage': len(accepted)/len(records),
            'accepted_accuracy': sum(r[key] == r['expected'] for r in accepted)/len(accepted) if accepted else None,
            'class_support': support, 'confusion_matrix': matrix, 'rows': labels, 'columns': labels+['unknown'],
            'f1': f1, 'macro_f1': sum(f1.values())/2 if all(support.values()) else None,
            'recall': {label: sum(r['expected'] == label and r[key] == label for r in records)/count if count else None
                       for label, count in support.items()},
            'both_reference_classes_present': all(support.values()),
            'scope_warning': None if all(support.values()) else
                             'single-reference-class subset: accuracy equals positive recall; specificity and overall accuracy unavailable'}


def legacy_prediction(predictor, observations):
    # v1 production had temporal quality checks, but no probability/jump rejection.
    if not observations:
        return 'unknown'
    obs = [o for o in observations if o.t >= observations[-1].t-9.85]
    if len(obs) < 40:
        return 'unknown'
    times = np.array([o.t for o in obs])
    coords = np.array([[o.cx, o.cy] for o in obs])
    if not np.isfinite(coords).all() or not np.isfinite(times).all():
        return 'unknown'
    if np.any(np.diff(times) <= 0) or np.max(np.diff(times)) > .65 or times[-1]-times[0] < 9.5:
        return 'unknown'
    target = np.linspace(times[-1]-9.8, times[-1], FRAMES)
    if target[0] < times[0]-.05:
        return 'unknown'
    sampled = np.column_stack([np.interp(target, times, coords[:, i]) for i in range(2)])
    with torch.inference_mode():
        index = int(predictor.model(torch.from_numpy(features(sampled, predictor.feature_version)[None])).argmax(-1))
    return LABELS[index]


def extract_sources(images_only=False):
    # Preserve paths within the intended dataset directory. Only dog JPEG/video files.
    images, videos = ROOT/'images', ROOT/'original_dog_videos'
    images.mkdir(exist_ok=True); videos.mkdir(exist_ok=True)
    for archive, output, accept in [
        (ROOT/'dog.tar.gz', images, lambda name: name.lower().endswith('.jpg')),
        (ROOT/'YTO_videos.tar.gz', videos,
         lambda name: bool(re.search(r'(?:\s|/)dog/', name.lower())) and name.lower().endswith(('.mp4', '.avi', '.flv')))
    ]:
        if images_only and output == videos:
            continue
        done = output/'extracted.json'
        if done.exists():
            continue
        names, seen = [], set()
        with tarfile.open(archive, mode='r|gz') as tar:
            for member in tar:
                if not member.isfile() or not accept(member.name):
                    continue
                target = output/Path(member.name).name
                if target.name in seen:
                    raise ValueError('duplicate archive basename; review extraction layout')
                seen.add(target.name)
                with tar.extractfile(member) as source, target.open('wb') as destination:
                    while chunk := source.read(1024*1024):
                        destination.write(chunk)
                names.append({'archive_member': member.name, 'filename': target.name, 'bytes': member.size})
        done.write_text(json.dumps(names, indent=2), encoding='utf-8')
        print(f'extracted {len(names)} from {archive.name}', flush=True)
    return images, videos


def run(input_mode='original', candidate=None, output=OUTPUT):
    torch.set_num_threads(2)
    output.mkdir(parents=True, exist_ok=True)
    images, videos = extract_sources()
    ranges = loadmat(ROOT/'ranges/dog/ranges.mat')['ranges']
    source_ranges = loadmat(ROOT/'YTO/Ranges/ranges_dog.mat')['ranges'].T
    predictors = {'v1': LSTMPredictor('artifacts/lstm/trajectory_lstm_v1_backup.pt'),
                  'v2': LSTMPredictor('artifacts/lstm/trajectory_lstm.pt')}
    records, excluded, source_info, seen_windows, used_ranges = [], [], {}, set(), {}
    checkpoint_paths = {'v1': Path('artifacts/lstm/trajectory_lstm_v1_backup.pt'),
                        'v2': Path('artifacts/lstm/trajectory_lstm.pt')}
    model_hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in checkpoint_paths.items()}
    if candidate:
        predictors['v3'] = LSTMPredictor(candidate)
        checkpoint_paths['v3'] = candidate
        model_hashes['v3'] = hashlib.sha256(candidate.read_bytes()).hexdigest()
    for video_id in sorted(set(source_ranges[:, 2])):
        files = [file for file in videos.iterdir() if file.stem == f'{int(video_id):04d}']
        if len(files) != 1:
            source_info[int(video_id)] = {'valid': False, 'reason': 'original video missing'}
            continue
        video = files[0]; capture = cv2.VideoCapture(str(video))
        fps = capture.get(cv2.CAP_PROP_FPS); count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        source_start = int(source_ranges[source_ranges[:, 2] == video_id, 0].min())
        source_end = int(source_ranges[source_ranges[:, 2] == video_id, 1].max())
        info = {'filename': video.name, 'fps': fps, 'native_frames': count,
                'dataset_frames': source_end-source_start+1, 'source_start': source_start,
                'sha256': hashlib.file_digest(video.open('rb'), 'sha256').hexdigest()}
        info['valid'] = capture.isOpened() and np.isfinite(fps) and fps > 0 and abs(count-info['dataset_frames']) <= 1
        capture.release(); source_info[int(video_id)] = info
    for shot_id, first, last in ranges:
        matches = source_ranges[(source_ranges[:, 0] == first) & (source_ranges[:, 1] == last)]
        if len(matches) != 1:
            excluded.append({'shot': int(shot_id), 'reason': 'shot/video index mismatch'}); continue
        video_id = int(matches[0, 2]); info = source_info[video_id]
        if not info.get('valid'):
            excluded.append({'shot': int(shot_id), 'reason': 'native FPS/frame correspondence unverified'}); continue
        annotations = loadmat(ROOT/f'behaviors/dogBehaviors/{shot_id:04d}.mat')['annotations'].ravel()
        if len(annotations) != last-first+1:
            excluded.append({'shot': int(shot_id), 'reason': 'label/frame count mismatch'}); continue
        fps = info['fps']; width_frames = int(np.ceil(FRAMES*fps/FPS))
        if len(annotations) < width_frames:
            excluded.append({'shot': int(shot_id), 'reason': 'shorter than native 10 seconds'}); continue
        detector = None
        for start in range(0, len(annotations)-width_frames+1, width_frames):
            references = [frame_reference(a.ravel()) for a in annotations[start:start+width_frames]]
            expected = max(['non_locomotion', 'locomotion'], key=references.count)
            purity = references.count(expected)/len(references)
            if purity < .9:
                excluded.append({'shot': int(shot_id), 'start': start, 'reason': 'mixed/unsupported reference labels'}); continue
            indices = first+start+np.rint(np.arange(FRAMES)*fps/FPS).astype(int)
            if any(int(indices[0]) <= end and int(indices[-1]) >= begin for begin, end in used_ranges.get(video_id, [])):
                excluded.append({'shot': int(shot_id), 'start': start, 'reason': 'overlapping evaluation window'}); continue
            frame_digest = hashlib.sha256()
            for index in indices:
                frame_digest.update((images/f'{int(index):08d}.jpg').read_bytes())
            digest = frame_digest.hexdigest()
            if digest in seen_windows:
                excluded.append({'shot': int(shot_id), 'start': start, 'reason': 'exact duplicate input window'}); continue
            # Verify actual video/JPEG frame correspondence independently of either LSTM.
            video_path = next(file for file in videos.iterdir() if file.stem == f'{video_id:04d}')
            capture = cv2.VideoCapture(str(video_path)); align_errors = []
            for global_index in [int(indices[0]), int(indices[-1])]:
                capture.set(cv2.CAP_PROP_POS_FRAMES, global_index-info['source_start'])
                ok, raw = capture.read(); jpeg = cv2.imread(str(images/f'{global_index:08d}.jpg'))
                if not ok or jpeg is None or abs(raw.shape[1]/raw.shape[0]-jpeg.shape[1]/jpeg.shape[0]) > .01:
                    align_errors.append(float('inf'))
                else:
                    # Publisher JPEGs are resized (e.g. 1280x720 -> 400x225).
                    raw = cv2.resize(raw, (jpeg.shape[1], jpeg.shape[0]), interpolation=cv2.INTER_AREA)
                    align_errors.append(float(np.abs(raw.astype(float)-jpeg.astype(float)).mean()))
            capture.release()
            if max(align_errors) > 10:
                excluded.append({'shot': int(shot_id), 'start': start, 'reason': 'original/JPEG alignment failed',
                                 'pixel_mae': [v if np.isfinite(v) else None for v in align_errors]}); continue
            detector = YOLO('artifacts/models/yolov8n.pt') if detector is None else detector
            # Reset tracking between non-overlapping evaluation windows.
            if getattr(detector, 'predictor', None) and hasattr(detector.predictor, 'trackers'):
                for tracker in detector.predictor.trackers:
                    tracker.reset()
            observations, target_id, multiple = [], None, False
            native = cv2.VideoCapture(str(video_path)) if input_mode == 'original' else None
            timestamps = []
            for i, global_index in enumerate(indices):
                if native is not None:
                    native.set(cv2.CAP_PROP_POS_FRAMES, int(global_index)-info['source_start'])
                    ok, frame = native.read()
                    timestamp = native.get(cv2.CAP_PROP_POS_MSEC)/1000
                    if not ok:
                        continue
                else:
                    frame = cv2.imread(str(images/f'{global_index:08d}.jpg'))
                    timestamp = float((global_index-info['source_start'])/fps)
                timestamps.append(timestamp)
                result = detector.track(frame, persist=True, classes=[16], tracker='bytetrack.yaml',
                                        conf=.1, verbose=False, imgsz=640)[0]
                boxes = result.boxes
                multiple |= int((boxes.conf >= .4).sum()) > 1
                if boxes.id is None:
                    continue
                ids = boxes.id.int().cpu().tolist(); xyxy = boxes.xyxy.cpu().numpy()
                if target_id is None and ids:
                    areas = (xyxy[:, 2]-xyxy[:, 0])*(xyxy[:, 3]-xyxy[:, 1]); target_id = ids[int(areas.argmax())]
                if target_id in ids:
                    x1, y1, x2, y2 = xyxy[ids.index(target_id)]; h, w = frame.shape[:2]
                    observations.append(Observation(float(timestamp-timestamps[0]), float((x1+x2)/2/w), float((y1+y2)/2/h)))
            if native is not None:
                native.release()
            if len(timestamps) != FRAMES or np.any(np.diff(timestamps) <= 0) or abs((timestamps[-1]-timestamps[0])-(indices[-1]-indices[0])/fps) > .05:
                excluded.append({'shot': int(shot_id), 'start': start, 'reason': 'native presentation timing unverified'}); continue
            if multiple:
                excluded.append({'shot': int(shot_id), 'start': start, 'reason': 'multiple-dog label identity ambiguous'}); continue
            stale = not observations or timestamps[-1]-timestamps[0]-observations[-1].t > .4
            v1 = 'unknown' if stale else legacy_prediction(predictors['v1'], observations)
            v2_raw = 'unknown' if stale else legacy_prediction(predictors['v2'], observations)
            v2 = {'label': 'unknown', 'reason': 'missing final track'} if stale else predictors['v2'].predict(observations)
            records.append({'shot': int(shot_id), 'video_id': video_id, 'first_frame': int(indices[0]),
                            'input_sha256': digest,
                            'last_frame': int(indices[-1]), 'native_fps': fps, 'expected': expected,
                            'reference_purity': purity, 'alignment_pixel_mae': align_errors,
                            'input_mode': input_mode, 'native_pts_start': timestamps[0], 'native_pts_end': timestamps[-1],
                            'tracked_samples': len(observations), 'v1_label': v1, 'v2_label': v2['label'],
                            'v1': coarse_prediction(v1), 'v2': coarse_prediction(v2['label']),
                            'v2_raw': coarse_prediction(v2_raw), 'v2_raw_label': v2_raw,
                            'v2_reason': v2.get('reason'),
                            'points': [{'t': o.t, 'cx': o.cx, 'cy': o.cy} for o in observations]})
            if candidate:
                v3 = {'label': 'unknown', 'reason': 'missing final track'} if stale else predictors['v3'].predict(observations)
                records[-1].update(v3=coarse_prediction(v3['label']), v3_label=v3['label'], v3_reason=v3.get('reason'))
            seen_windows.add(digest); used_ranges.setdefault(video_id, []).append((int(indices[0]), int(indices[-1])))
            (output/f'shot_{shot_id}_{start}_preview.jpg').write_bytes(cv2.imencode('.jpg', cv2.imread(str(images/f'{int(indices[0]):08d}.jpg')))[1].tobytes())
            print(f'shot={shot_id} reference={expected} v1={v1} v2={v2["label"]} tracked={len(observations)}', flush=True)
    report = {'task': 'publisher-labeled coarse locomotion subset; NOT four-class accuracy',
              'four_class_behavior_accuracy': None,
              'input_mode': input_mode,
              'reference_policy': {'locomotion_label_ids': sorted(LOCOMOTION), 'local_only_label_ids': sorted(LOCAL_ONLY),
                                   'minimum_label_purity': .9, 'unannotated': 'excluded', 'native_window_seconds': 10},
              'metrics': {name: classification_metrics(records, name) for name in ['v1', 'v2_raw', 'v2']+(['v3'] if candidate else [])},
              'records': records, 'excluded': excluded, 'original_videos': source_info,
              'model_sha256': model_hashes,
              'source': 'https://calvin-vision.net/datasets/tigdog/', 'license': 'non-commercial research only',
              'limitations': ['coarse label mapping, no independent 4-class ground truth',
                              'largest tracked dog approximates publisher nearest-dog annotation',
                              'camera motion uncompensated', 'small, eligibility-selected subset',
                              'detector upstream pretraining overlap with internet sources cannot be ruled out']}
    if records:
        report['accuracy_change_percentage_points'] = 100*(report['metrics']['v2']['accuracy']-report['metrics']['v1']['accuracy'])
        groups = sorted({r['video_id'] for r in records})
        if len(groups) >= 2:
            pairs = np.array([[np.mean([r['v1'] == r['expected'] for r in records if r['video_id'] == group]),
                               np.mean([r['v2'] == r['expected'] for r in records if r['video_id'] == group])]
                              for group in groups])
            rng = np.random.default_rng(20261011)
            samples = pairs[rng.integers(0, len(pairs), (10000, len(pairs)))].mean(1)
            report['paired_bootstrap'] = {'unit': 'source_video', 'groups': len(groups),
                                          'equal_video_accuracy_change_pp': float(100*np.mean(pairs[:, 1]-pairs[:, 0])),
                                          'exploratory_95_ci_pp': np.percentile(100*(samples[:, 1]-samples[:, 0]), [2.5, 97.5]).tolist()}
    if any(hashlib.sha256(path.read_bytes()).hexdigest() != model_hashes[name] for name, path in checkpoint_paths.items()):
        raise ValueError('model changed during evaluation')
    if candidate and records:
        report['candidate_change_percentage_points'] = 100*(report['metrics']['v3']['accuracy']-report['metrics']['v2']['accuracy'])
        report['candidate_evaluation_scope'] = 'previously examined development subset; not a new blind test'
    (output/'evaluation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (output/f'evaluation_{input_mode}.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'metrics': report['metrics'], 'excluded': len(excluded),
                      'accuracy_change_percentage_points': report.get('accuracy_change_percentage_points')}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--prepare-images-only', action='store_true')
    parser.add_argument('--input-mode', choices=['original', 'jpeg'], default='original')
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    if args.prepare_images_only:
        extract_sources(images_only=True)
    else:
        run(args.input_mode, args.candidate, args.output)
