"""Pinned InterPet4D root trajectories for existing LSTM pretraining.

Motion is an automated SMAL fit, NOT manually labeled four-class behavior.
Use original frame indices and publisher temporal segments; split by dog.
"""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import requests

from pet_monitor.lstm import FPS, FRAMES

ROOT = Path('artifacts/datasets/interpet4d')
REPO = 'https://huggingface.co/datasets/ohicarip/interpet4d'


def fetch(name, revision):
    path = (ROOT/name).resolve()
    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError('dataset path escapes local cache')
    if not path.exists():
        response = requests.get(f'{REPO}/resolve/{revision}/{name}', timeout=60)
        response.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_suffix(path.suffix+'.part')
        part.write_bytes(response.content); part.replace(path)
    return path


def build_windows(root, frame_idx, segments, weights, reprojection, source_fps):
    if root.ndim != 2 or root.shape[1] != 3 or len(root) != len(frame_idx):
        raise ValueError('invalid root/frame shape')
    if source_fps <= 0 or not np.isfinite(root).all() or np.any(np.diff(frame_idx) <= 0):
        raise ValueError('invalid coordinates/timing')
    if len(weights) != len(root) or len(reprojection) != len(root):
        raise ValueError('quality length mismatch')
    windows, starts = [], []
    for begin, end in segments:
        begin, end = int(begin), int(end)
        if not 0 <= begin < end <= len(root):
            raise ValueError('invalid temporal segment')
        times = frame_idx[begin:end]/source_fps
        if len(times) < 2 or np.max(np.diff(times)) > .2:
            continue
        for start in np.arange(times[0], times[-1]-(FRAMES-1)/FPS+1e-6, FRAMES/FPS):
            target = start+np.arange(FRAMES)/FPS
            selected = (times >= start-.04) & (times <= target[-1]+.04)
            quality = weights[begin:end][selected]
            residual = reprojection[begin:end][selected]
            if not len(quality) or np.mean(quality >= .5) < .9 or not np.isfinite(residual).all() or np.median(residual) > 40:
                continue
            coords = np.column_stack([np.interp(target, times, root[begin:end, i]) for i in range(2)])
            windows.append(coords); starts.append(float(start))
    return windows, starts


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    metadata = requests.get('https://huggingface.co/api/datasets/ohicarip/interpet4d', timeout=30)
    metadata.raise_for_status()
    # Preserve an existing pinned revision for reproducibility.
    repository_path = ROOT/'repository.json'
    if not repository_path.exists():
        repository_path.write_text(json.dumps(metadata.json(), indent=2), encoding='utf-8')
    revision = json.loads(repository_path.read_text())['sha']
    source = json.loads(fetch('cleanup_smal/manifest.json', revision).read_text(encoding='utf-8'))
    dogs = sorted({clip['clip_id'].split('_')[0] for clip in source['clips']})
    np.random.default_rng(20261011).shuffle(dogs)
    assignments = {dog: 'train' if i < len(dogs)-4 else 'validation' if i < len(dogs)-2 else 'test'
                   for i, dog in enumerate(dogs)}
    paths = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(fetch, 'cleanup_smal/'+clip['path'], revision): clip for clip in source['clips']}
        for i, job in enumerate(as_completed(jobs), 1):
            clip = jobs[job]; paths[clip['clip_id']] = job.result()
            if i % 50 == 0:
                print(f'pose clips downloaded {i}/{len(jobs)}', flush=True)
    coords, splits, groups, clips, starts, files, excluded, hashes = [], [], [], [], [], [], [], set()
    window_hashes = set()
    for clip in source['clips']:
        clip_id = clip['clip_id']; dog = clip_id.split('_')[0]; path = paths[clip_id]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in hashes:
            excluded.append({'clip': clip_id, 'reason': 'duplicate file'}); continue
        hashes.add(digest)
        with np.load(path, allow_pickle=False) as values:
            windows, seconds = build_windows(values['root_translation'], values['frame_idx'],
                                              values['segments'], values['quality_weight'],
                                              values['reprojection_px'], source['source_fps'])
        files.append({'clip': clip_id, 'dog': dog, 'split': assignments[dog], 'sha256': digest,
                      'source_split': clip['split'], 'windows': len(windows)})
        if not windows:
            excluded.append({'clip': clip_id, 'reason': 'no quality-qualified native 10-second window'})
        for window, start in zip(windows, seconds):
            key = hashlib.sha256(np.round(window-window[:1], 5).tobytes()).hexdigest()
            if key in window_hashes:
                excluded.append({'clip': clip_id, 'start': start, 'reason': 'duplicate centered trajectory window'}); continue
            window_hashes.add(key)
            coords.append(window); splits.append(assignments[dog]); groups.append(dog); clips.append(clip_id); starts.append(start)
    if not coords or any(split not in splits for split in ['train', 'validation', 'test']):
        raise ValueError('empty dog-separated split; do not silently mix dogs or warp time')
    np.savez_compressed(ROOT/'windows.npz', coords=np.asarray(coords, dtype=np.float32), splits=np.asarray(splits),
                        groups=np.asarray(groups), clips=np.asarray(clips), starts=np.asarray(starts))
    manifest = {'dataset': 'InterPet4D v1.1 cleaned SMAL root motion', 'source': REPO, 'revision': revision,
                'license': 'CC BY-NC 4.0', 'source_fps': source['source_fps'], 'fps': FPS, 'frames': FRAMES,
                'projection_scale': 10, 'coordinate_units': 'publisher dog body units, world Z up',
                'role': 'unlabeled pretraining; automated pose fits, not behavior ground truth',
                'split_seed': 20261011, 'split_unit': 'dog', 'dog_assignments': assignments,
                'window_counts': {split: splits.count(split) for split in ['train', 'validation', 'test']},
                'quality_policy': {'respect_publisher_segments': True, 'max_native_gap_s': .2,
                                   'minimum_quality_fraction': .9, 'median_reprojection_px_max': 40},
                'windows_sha256': hashlib.sha256((ROOT/'windows.npz').read_bytes()).hexdigest(),
                'archive_sha256': hashlib.sha256((ROOT/'cleanup_smal/manifest.json').read_bytes()).hexdigest(),
                'archive_hash_scope': 'publisher manifest; not a full archive', 'files': files, 'excluded': excluded,
                'limitations': ['automatically fitted motion can contain errors', 'world root differs from camera box center',
                                'no independent four-class temporal behavior labels']}
    (ROOT/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps({'revision': revision, 'dogs': assignments, 'windows': manifest['window_counts']}), flush=True)


if __name__ == '__main__':
    main()
