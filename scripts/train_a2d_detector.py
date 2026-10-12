"""Fine-tune YOLO on A2D's publisher dog boxes; keep test clips held out."""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import torch
from ultralytics import YOLO

from pet_monitor.detection import unique_dog_indices
from scripts.prepare_a2d import sha256
from scripts.prepare_a2d_detector import OUTPUT


def overlap(a, b):
    x1, y1 = np.maximum(a[:2], b[:2])
    x2, y2 = np.minimum(a[2:], b[2:])
    intersection = max(0, x2-x1)*max(0, y2-y1)
    area_a = max(0, a[2]-a[0])*max(0, a[3]-a[1])
    area_b = max(0, b[2]-b[0])*max(0, b[3]-b[1])
    return intersection/(area_a+area_b-intersection) if area_a+area_b-intersection else 0


def detections(model, model_class, split):
    # The COCO base model uses dog class 16, whereas the fine-tuned model has
    # one class, dog 0. The ordinary YOLO validator would compare unlike IDs.
    records = []
    for image_path in sorted((OUTPUT / 'images' / split).glob('*.jpg')):
        frame = cv2.imread(str(image_path))
        if frame is None:
            raise ValueError(f'cannot read A2D test image: {image_path}')
        height, width = frame.shape[:2]
        gt = []
        for line in (OUTPUT / 'labels' / split / f'{image_path.stem}.txt').read_text().splitlines():
            label, cx, cy, w, h = map(float, line.split())
            if label != 0:
                raise ValueError('A2D test label is not dog')
            gt.append(np.array([(cx-w/2)*width, (cy-h/2)*height,
                                (cx+w/2)*width, (cy+h/2)*height]))
        result = model.predict(frame, classes=[model_class], conf=.05, imgsz=416, verbose=False)[0]
        boxes = result.boxes.xyxy.cpu().numpy()
        scores = result.boxes.conf.cpu().numpy()
        kept = unique_dog_indices(boxes, scores)
        records.append((gt, boxes[kept], scores[kept]))
    return records


def measures(records, threshold):
    tp = fp = fn = frames_with_dog = 0
    for gt, predicted, scores in records:
        matched = set()
        for index in np.argsort(-scores):
            if scores[index] < threshold:
                continue
            choices = sorted(((overlap(predicted[index], box), k) for k, box in enumerate(gt)
                              if k not in matched), reverse=True)
            if choices and choices[0][0] >= .5:
                tp += 1
                matched.add(choices[0][1])
            else:
                fp += 1
        fn += len(gt)-len(matched)
        frames_with_dog += bool(matched)
    return {'tp': tp, 'fp': fp, 'fn': fn,
            'precision': tp/(tp+fp) if tp+fp else None,
            'recall': tp/(tp+fn) if tp+fn else None,
            'frames_with_matched_dog': frames_with_dog,
            'threshold': threshold, 'match_rule': 'class-specific detections, IoU >=0.5; one-to-one box matching'}


def choose_threshold(records):
    candidates = [(measures(records, threshold), threshold) for threshold in
                  (.1, .15, .2, .25, .3, .4, .5, .6, .7, .8)]
    eligible = [(m['recall'], -threshold, threshold) for m, threshold in candidates
                if m['precision'] is not None and m['precision'] >= .8]
    return max(eligible)[2] if eligible else 1.0


def run(train=True):
    manifest = json.loads((OUTPUT / 'manifest.json').read_text(encoding='utf-8'))
    if set(manifest['image_counts']) != {'train', 'val', 'test'}:
        raise ValueError('A2D detector needs all three splits')
    torch.set_num_threads(4)
    base = Path('artifacts/models/yolov8n.pt')
    if not base.exists():
        raise FileNotFoundError(base)
    output = Path('artifacts/a2d_detector').resolve()
    if train:
        model = YOLO(str(base))
        model.train(data=str(OUTPUT / 'data.yaml'), epochs=5, imgsz=416, batch=8, device='cpu',
                    workers=0, project=str(output), name='trial',
                    exist_ok=True, plots=False, verbose=False, patience=5)
    candidate = output / 'trial/weights/best.pt'
    if not candidate.exists():
        raise FileNotFoundError(candidate)
    # Both models see publisher test only after training and checkpoint choice.
    baseline = YOLO(str(base)); fitted = YOLO(str(candidate))
    base_threshold = choose_threshold(detections(baseline, 16, 'val'))
    fitted_threshold = choose_threshold(detections(fitted, 0, 'val'))
    base_test = detections(baseline, 16, 'test')
    fitted_test = detections(fitted, 0, 'test')
    report = {'task': 'A2D annotated dog detection, not behavior recognition',
              'test_frames': manifest['image_counts']['test'],
              'test_clips': manifest['clip_counts']['test'],
              'training_images': manifest['image_counts']['train'],
              'validation_images': manifest['image_counts']['val'],
              'base_sha256': sha256(base), 'candidate_sha256': sha256(candidate),
              'threshold_selection': 'validation precision >=0.8 then maximum recall; duplicate partial boxes suppressed',
              'base': measures(base_test, .15),
              'candidate': measures(fitted_test, .15),
              'base_calibrated': measures(base_test, base_threshold),
              'candidate_calibrated': measures(fitted_test, fitted_threshold),
              'candidate_at_0_5': measures(fitted_test, .5),
              'validation_calibrated': {'base': measures(detections(baseline, 16, 'val'), base_threshold),
                                        'candidate': measures(detections(fitted, 0, 'val'), fitted_threshold)},
              'validation_candidate_at_0_5': measures(detections(fitted, 0, 'val'), .5)}
    path = output / 'evaluation.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--evaluate-only', action='store_true')
    args = parser.parse_args()
    run(train=not args.evaluate_only)
