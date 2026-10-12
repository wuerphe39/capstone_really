"""Prepare A2D's annotated dog frames for an isolated YOLO experiment.

All frames from one publisher clip remain in one split. The publisher test
clips are never used by the trainer or its validation checkpoint selection.
"""
import json
from collections import Counter
from pathlib import Path

import cv2
import h5py
import numpy as np

from scripts.prepare_a2d import ROOT, sha256

OUTPUT = ROOT / 'detector'


def dog_boxes(annotation):
    with h5py.File(annotation, 'r') as mat:
        names = [''.join(chr(c) for c in mat[ref][:].ravel()) for ref in mat['class'][0]]
        boxes = mat['reBBox'][:].T
    if len(names) != len(boxes):
        raise ValueError('A2D class/box count mismatch')
    return [box for name, box in zip(names, boxes) if name.startswith('dog-')]


def run():
    source = ROOT / 'manifest.json'
    manifest = json.loads(source.read_text(encoding='utf-8'))
    if not manifest['records']:
        raise ValueError('empty selected A2D manifest')
    train_ids = sorted(row['id'] for row in manifest['records'] if row['split'] == 'train')
    validation = set(np.random.default_rng(20261011).choice(train_ids, size=round(.2*len(train_ids)), replace=False))
    records = []
    for row in manifest['records']:
        clip_id = row['id']
        split = 'test' if row['split'] == 'test' else ('val' if clip_id in validation else 'train')
        clip = ROOT / 'selected_clips' / f'{clip_id}.mp4'
        if sha256(clip) != row['sha256']:
            raise ValueError('A2D clip checksum mismatch')
        annotations = sorted((ROOT / 'annotations' / clip_id).glob('*.mat'))
        if not annotations:
            raise ValueError(f'missing official annotation: {clip_id}')
        capture = cv2.VideoCapture(str(clip))
        try:
            for annotation in annotations:
                # Publisher MATLAB frame numbers begin at one.
                capture.set(cv2.CAP_PROP_POS_FRAMES, int(annotation.stem)-1)
                okay, frame = capture.read()
                if not okay:
                    raise ValueError(f'cannot decode annotation frame: {annotation}')
                height, width = frame.shape[:2]
                labels = []
                for box in dog_boxes(annotation):
                    x1, y1, x2, y2 = np.asarray(box, dtype=float)
                    x1, x2 = np.clip([x1, x2], 0, width)
                    y1, y2 = np.clip([y1, y2], 0, height)
                    if x2-x1 < 2 or y2-y1 < 2:
                        raise ValueError(f'invalid dog box: {annotation}')
                    labels.append(f'0 {(x1+x2)/(2*width):.8f} {(y1+y2)/(2*height):.8f} {(x2-x1)/width:.8f} {(y2-y1)/height:.8f}')
                if not labels:
                    raise ValueError(f'no dog actor in selected annotation: {annotation}')
                stem = f'{clip_id}_{annotation.stem}'
                image_path = OUTPUT / 'images' / split / f'{stem}.jpg'
                label_path = OUTPUT / 'labels' / split / f'{stem}.txt'
                image_path.parent.mkdir(parents=True, exist_ok=True)
                label_path.parent.mkdir(parents=True, exist_ok=True)
                if not cv2.imwrite(str(image_path), frame):
                    raise ValueError(f'cannot save frame: {image_path}')
                label_path.write_text('\n'.join(labels)+'\n', encoding='ascii')
                records.append({'clip_id': clip_id, 'frame': int(annotation.stem), 'split': split,
                                'action': row['action'], 'dog_boxes': len(labels)})
        finally:
            capture.release()
    yaml = 'path: ' + OUTPUT.resolve().as_posix() + '\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n  0: dog\n'
    (OUTPUT / 'data.yaml').write_text(yaml, encoding='ascii')
    report = {'dataset': 'A2D publisher dog actor boxes', 'source_manifest_sha256': sha256(source),
              'split_rule': 'publisher test intact; 20% publisher train clip IDs randomly assigned validation before fitting',
              'image_counts': dict(Counter(item['split'] for item in records)),
              'clip_counts': dict(Counter('test' if row['split'] == 'test' else ('val' if row['id'] in validation else 'train')
                                          for row in manifest['records'])),
              'records': records}
    (OUTPUT / 'manifest.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'images': len(records), 'image_counts': report['image_counts'],
                      'clip_counts': report['clip_counts']}), flush=True)


if __name__ == '__main__':
    run()
