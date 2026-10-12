"""Train an AudioSet-augmented YAMNet embedding LSTM; keep runtime unchanged."""
import hashlib
import argparse
import json
from pathlib import Path

import numpy as np
import torch

import scripts.train_yamnet_bark_lstm as baseline_training
from scripts.train_yamnet_bark_lstm import (
    ROOT as BASE_ROOT, load_rows, measure, normalize_and_pad, predict, train,
)


ROOT = Path('artifacts/audioset_bark_strong')


def window_label(intervals, index):
    start, end = index*5, (index+1)*5
    overlap = sum(max(0, min(end, stop)-max(start, onset))
                  for onset, stop in intervals)
    return int(overlap >= .1)


def strong_windows(manifest, extraction):
    windows = []
    for row in manifest['rows']['train']:
        path = Path(row['path'])
        if hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
            raise ValueError(f'AudioSet source checksum mismatch: {row["clip_id"]}')
        with np.load(ROOT/'features'/(row['sha256']+'.npz')) as data:
            if (int(data['version']) != 3 or
                    str(data['model_sha256']) != extraction['model_sha256']):
                raise ValueError(f'YAMNet feature mismatch: {row["clip_id"]}')
            pieces = np.split(data['embeddings'].astype(np.float32),
                              np.cumsum(data['lengths'].astype(int))[:-1])
        if len(pieces) != 2:
            raise ValueError(f'expected two 5-second windows: {row["clip_id"]}')
        for index, piece in enumerate(pieces):
            windows.append({'id': row['clip_id']+f':{index}',
                            'source_id': row['video_id'], 'source': 'audioset_strong_train',
                            'label': window_label(row['bark_intervals_s'], index),
                            'pieces': [piece]})
    return windows


def main(seed=20261012):
    torch.set_num_threads(2)
    np.random.seed(seed)
    baseline_training.SEED = seed
    base, base_extraction = load_rows()
    manifest_path = ROOT/'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    extra_extraction = json.loads((ROOT/'extraction.json').read_text(encoding='utf-8'))
    if (extra_extraction['model_sha256'] != base_extraction['model_sha256'] or
            extra_extraction['manifest_sha256'] != hashlib.sha256(manifest_path.read_bytes()).hexdigest()):
        raise ValueError('YAMNet model or AudioSet manifest changed after extraction')
    extra = strong_windows(manifest, extra_extraction)
    if not any(row['label'] for row in extra):
        raise ValueError('no positive Bark windows')
    baseline = json.loads((BASE_ROOT/'comparison.json').read_text(encoding='utf-8'))
    fpr_limit = float(baseline['selection_rule'].split('<= ')[1].split(';')[0])
    augmented = {split: list(items) for split, items in base.items()}
    augmented['train'].extend(extra)
    mean, std, max_patches = normalize_and_pad(augmented)
    model, best, history = train('lstm', augmented, fpr_limit)
    val_scores, _ = predict(model, augmented['val'])
    eval_scores, inference_s = predict(model, augmented['eval'])
    threshold = best['validation']['threshold']
    direct = baseline['comparison']['yamnet_bark']
    old_lstm = baseline['comparison']['yamnet_embedding_lstm']
    report = {
        'task': 'YAMNet embedding LSTM with AudioSet strong-label train augmentation',
        'seed': seed,
        'train_extra': {'clips': len(manifest['rows']['train']), 'windows': len(extra),
                        'bark_windows': sum(row['label'] for row in extra),
                        'negative_windows': sum(not row['label'] for row in extra),
                        'distinct_video_ids': len({row['source_id'] for row in extra}),
                        'manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest()},
        'selection_rule': baseline['selection_rule'],
        'augmented_lstm': {'epoch': best['epoch'], 'threshold': threshold,
                           'val': measure(augmented['val'], val_scores, threshold),
                           'eval': measure(augmented['eval'], eval_scores, threshold),
                           'eval_inference_s': inference_s, 'history': history},
        'original_lstm': {'val': old_lstm['val'], 'eval': old_lstm['eval']},
        'yamnet_direct': {'val': direct['val'], 'eval': direct['eval']},
        'limitations': ['FSD/ESC evaluation was previously inspected: development comparison only',
                        'YAMNet pretrained on AudioSet; this is not an independent AudioSet test',
                        'AudioSet source overlap with FSD/ESC is not fully known',
                        'Only obtainable AudioSet clips were sampled; home microphone transfer is untested'],
        'promoted': False,
    }
    suffix = '' if seed == 20261012 else f'_seed{seed}'
    torch.save({'kind': 'lstm', 'state_dict': model.state_dict(),
                'mean': torch.from_numpy(mean), 'std': torch.from_numpy(std),
                'max_patches': max_patches, 'threshold': threshold,
                'yamnet_model_sha256': base_extraction['model_sha256'],
                'training_scope': 'FSD Bark and AudioSet strong-label train windows'},
               ROOT/f'yamnet_embedding_lstm_audioset{suffix}.pt')
    (ROOT/f'comparison{suffix}.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'seed': seed, 'train_extra': report['train_extra'],
                      'validation': report['augmented_lstm']['val'],
                      'evaluation': report['augmented_lstm']['eval']},
                     ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=int, default=20261012)
    main(parser.parse_args().seed)
