"""Extract only unambiguous dog eating/walking/running clips from official A2D.

The publisher's 'none' action is not a still label. This script never maps it
to one. Original videos stay under the ignored artifacts directory.
"""
import hashlib
import json
import re
import shutil
import tarfile
from collections import Counter
from pathlib import Path

import cv2
import h5py

ROOT = Path('artifacts/datasets/a2d')
ARCHIVE = ROOT / 'A2D_main_1_0.tar.bz'
EVAL_ARCHIVE = ROOT / 'A2D_eval_1_0.tar.bz'
EVALUATION = ROOT / 'eval/Release/AR.mat'
CLIPS = ROOT / 'selected_clips'
ACTIONS = {73: 'eating', 77: 'running', 78: 'walking'}
SOURCE = 'https://web.eecs.umich.edu/~jjcorso/r/a2d/'


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def ensure_evaluation():
    if EVALUATION.exists():
        return
    if not EVAL_ARCHIVE.exists():
        raise FileNotFoundError('Download the official A2D evaluation archive')
    with tarfile.open(EVAL_ARCHIVE, 'r:bz2') as archive:
        member = archive.getmember('Release/AR.mat')
        if not member.isfile():
            raise ValueError('publisher action labels are not a regular file')
        source = archive.extractfile(member)
        if source is None:
            raise ValueError('cannot read publisher action labels')
        EVALUATION.parent.mkdir(parents=True, exist_ok=True)
        with EVALUATION.open('wb') as target:
            shutil.copyfileobj(source, target)
        if EVALUATION.stat().st_size != member.size:
            raise ValueError('publisher action label size mismatch')


def labels(path=EVALUATION):
    records = {}
    with h5py.File(path) as h5:
        values = h5['AR']
        for i, label in enumerate(values['single'][0].astype(int)):
            if label not in ACTIONS:
                continue
            action_set = h5[values['multiple'][0, i]][:].astype(int).ravel().tolist()
            if action_set != [label]:
                continue  # Multi-action videos do not have a pure clip label.
            name = ''.join(chr(c) for c in h5[values['vid'][0, i]][:, 0])
            if not re.fullmatch(r'[A-Za-z0-9_-]{11}', name):
                raise ValueError('invalid publisher clip ID')
            if name in records:
                raise ValueError('duplicate publisher clip ID')
            records[name] = {'id': name, 'action': ACTIONS[label], 'label_id': int(label),
                             'split': 'test' if values['test'][0, i] else 'train'}
    return records


def run():
    if not ARCHIVE.exists():
        raise FileNotFoundError('Download the official A2D main archive first')
    ensure_evaluation()
    records = labels()
    wanted = {f'Release/clips320H/{name}.mp4': name for name in records}
    CLIPS.mkdir(parents=True, exist_ok=True)
    seen = set()
    with tarfile.open(ARCHIVE, 'r:bz2') as archive:
        for member in archive:
            name = wanted.get(member.name)
            if name is None:
                continue
            if not member.isfile() or name in seen:
                raise ValueError('invalid or repeated selected archive member')
            source = archive.extractfile(member)
            if source is None:
                raise ValueError('selected video cannot be read')
            path = CLIPS / f'{name}.mp4'
            temporary = path.with_suffix('.mp4.part')
            with temporary.open('wb') as target:
                shutil.copyfileobj(source, target)
            if temporary.stat().st_size != member.size:
                raise ValueError('selected video size mismatch')
            temporary.replace(path)
            seen.add(name)
    if seen != set(records):
        raise ValueError(f'A2D archive missing {len(set(records)-seen)} selected clips')
    for name, record in records.items():
        path = CLIPS / f'{name}.mp4'
        capture = cv2.VideoCapture(str(path))
        fps = capture.get(cv2.CAP_PROP_FPS)
        frames = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        opened = capture.isOpened()
        capture.release()
        record.update({'sha256': sha256(path), 'fps': float(fps), 'frames': int(frames),
                       'duration_s': float(frames/fps) if opened and fps > 0 else None,
                       'decoded_metadata_valid': bool(opened and fps > 0 and frames > 0)})
    report = {'dataset': 'A2D actor-action v1.0', 'source': SOURCE,
              'license': 'scientific research; noncommercial; no redistribution',
              'archive_bytes': ARCHIVE.stat().st_size, 'archive_sha256': sha256(ARCHIVE),
              'evaluation_sha256': sha256(EVALUATION),
              'selection': 'one publisher actor-action label, dog-eating/running/walking only',
              'counts': dict(Counter(f"{r['split']}:{r['action']}" for r in records.values())),
              'records': list(records.values())}
    (ROOT / 'manifest.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'selected': len(records), 'counts': report['counts'],
                      'metadata_invalid': sum(not r['decoded_metadata_valid'] for r in records.values()),
                      'archive_sha256': report['archive_sha256']}), flush=True)


if __name__ == '__main__':
    run()
