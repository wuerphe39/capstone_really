"""Official, licensed dog mocap -> unlabeled next-step LSTM pretraining windows.

No behavioral labels are inferred. Recording families remain in one split.
World X/Z root motion is projected to 2D; it is NOT a camera bounding-box track.
"""
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

import numpy as np
import requests

from pet_monitor.lstm import FPS, FRAMES

URL = 'https://starke-consult.de/AI4Animation/SIGGRAPH_2018/MotionCapture.zip'
SHA256 = '0ecd909b673cfca5e20c3f568376dcf27d7da3bd153957c2b034d95af366132a'
ROOT = Path('artifacts/datasets/ai4animation')


def read_root(content):
    text = content.decode('utf-8').replace('\r', '')
    header, motion = text.split('MOTION', 1)
    channels = re.findall(r'CHANNELS\s+(\d+)\s+([^\n]+)', header)
    if not channels or channels[0][1].split()[:3] != ['Xposition', 'Yposition', 'Zposition']:
        raise ValueError('unsupported BVH root channel order')
    count = int(re.search(r'Frames:\s*(\d+)', motion)[1])
    match = re.search(r'Frame Time:\s*([\d.eE+-]+)', motion)
    dt = float(match[1])
    data = np.loadtxt(io.StringIO(motion[match.end():]), ndmin=2)
    if dt <= 0 or not np.isfinite(dt) or data.shape != (count, sum(int(n) for n, _ in channels)):
        raise ValueError('invalid BVH timing/frame/channel count')
    if not np.isfinite(data).all():
        raise ValueError('non-finite BVH samples')
    return data[:, [0, 2]], dt


def recording_group(name):
    # Multiple KAN clips / mirrored suffixes from the same recording must not leak.
    match = re.match(r'(D\d+_[A-Za-z]*\d+)[a-z]*_', name)
    if not match:
        raise ValueError(f'unknown recording identity: {name}')
    return match[1]


def prepare():
    ROOT.mkdir(parents=True, exist_ok=True)
    archive = ROOT.parent / 'AI4Animation_MotionCapture.zip'
    if not archive.exists():
        part = archive.with_suffix('.part')
        with requests.get(URL, stream=True, timeout=60) as response:
            response.raise_for_status()
            with part.open('wb') as stream:
                for chunk in response.iter_content(1024*1024):
                    stream.write(chunk)
        part.replace(archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != SHA256:
        raise ValueError('archive changed; review source/version before using it')
    arrays, names, seen, rejected = {}, [], {}, []
    with zipfile.ZipFile(archive) as source:
        for name in sorted(source.namelist()):
            if not name.endswith('.bvh'):
                continue
            content = source.read(name)
            file_hash = hashlib.sha256(content).hexdigest()
            if file_hash in seen:
                rejected.append({'name': name, 'reason': 'duplicate_bytes', 'duplicate_of': seen[file_hash]})
                continue
            coords, dt = read_root(content)
            # Also detect identical root motion despite different skeleton/metadata bytes.
            motion_hash = hashlib.sha256(np.round(coords-coords[:1], 4).tobytes()).hexdigest()
            if motion_hash in seen:
                rejected.append({'name': name, 'reason': 'duplicate_root_motion', 'duplicate_of': seen[motion_hash]})
                continue
            seen[file_hash] = seen[motion_hash] = name
            target = np.arange(0, (len(coords)-1)*dt, 1/FPS)
            sampled = np.column_stack([np.interp(target, np.arange(len(coords))*dt, coords[:, i]) for i in range(2)])
            arrays[name] = sampled
            names.append({'name': name, 'sha256': file_hash, 'motion_sha256': motion_hash,
                          'group': recording_group(name), 'native_fps': 1/dt,
                          'native_frames': len(coords), 'duration_s': (len(coords)-1)*dt})
    groups = sorted({item['group'] for item in names})
    np.random.default_rng(2026).shuffle(groups)
    assignments = {group: 'train' if i < int(len(groups)*.7) else
                   'validation' if i < int(len(groups)*.85) else 'test' for i, group in enumerate(groups)}
    windows, splits, identities = [], [], []
    for item in names:
        item['split'] = assignments[item['group']]
        coords = arrays[item['name']]
        # Non-overlapping 10-second windows; augmentation takes place later, on train only.
        for offset in range(0, len(coords)-FRAMES+1, FRAMES):
            windows.append(coords[offset:offset+FRAMES])
            splits.append(item['split'])
            identities.append(item['group'])
    np.savez_compressed(ROOT / 'windows.npz', coords=np.asarray(windows, dtype=np.float32),
                        splits=np.asarray(splits), groups=np.asarray(identities))
    manifest = {'dataset': 'AI4Animation SIGGRAPH 2018 dog motion capture', 'url': URL,
                'source': 'https://github.com/sebastianstarke/AI4Animation',
                'source_commit': '98aff6c87d73e4af0cbf50df2586f58532475662',
                'archive_sha256': digest, 'archive_bytes': archive.stat().st_size,
                'windows_sha256': hashlib.sha256((ROOT / 'windows.npz').read_bytes()).hexdigest(),
                'license': 'CC BY-NC 4.0; research/education; no commercial use',
                'attribution': 'Sebastian Starke et al., Mode-Adaptive Neural Networks for Quadruped Motion Control, SIGGRAPH 2018; motion capture provided by Bandai-Namco Studios',
                'role': 'unlabeled self-supervised pretraining only', 'behavior_labels': None,
                'fps': FPS, 'frames_per_window': FRAMES, 'split_seed': 2026,
                'split_unit': 'recording_family', 'files': names, 'rejected': rejected,
                'window_counts': {split: splits.count(split) for split in ['train', 'validation', 'test']},
                'limitations': ['one captured dog: NOT independent-dog evaluation',
                                'world-plane root projection differs from camera box center',
                                'no still/moving/spinning/pacing ground truth',
                                'hash checks detect exact duplicates, not all near duplicates']}
    (ROOT / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps({'files': len(names), 'groups': len(groups), 'windows': manifest['window_counts'],
                      'rejected': len(rejected)}), flush=True)


if __name__ == '__main__':
    prepare()
