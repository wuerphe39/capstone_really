"""Compare a frozen audio LSTM, validation-only threshold tuning and MIL augmentation.

All candidate selection uses ESC validation and the official FSD dev/val split.
Previously inspected ESC test and FSD eval remain development comparisons, not blind tests.
"""
import copy
import hashlib
import io
import json
import time
from math import gcd
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from scipy.signal import resample_poly
from torch.nn import functional as F

from pet_monitor.audio_lstm import AudioClassifier, binary_metrics, logmel
from scripts.train_audio_mil import assert_disjoint, bag_logits, features

ESC = Path('artifacts/datasets/esc50')
FSD = Path('artifacts/datasets/fsd50k')
MODELS = Path('artifacts/audio_lstm')
REPORT = Path('docs/evidence/audio_lstm_three_way.json')


def load_group(root, manifest, partition=None):
    rows = json.loads(manifest.read_text(encoding='utf-8'))['records']
    if partition:
        rows = [r for r in rows if r['split'] == partition]
    return [{**r, 'source_id': str(r.get('source_id', r.get('src_file'))),
             'expected': int(r.get('expected', r.get('category') == 'dog')),
             'path': root / ('audio' if root == ESC else '') / r['filename']} for r in rows]


def groups():
    esc = load_group(ESC, ESC/'manifest.json')
    result = {name: [r for r in esc if r['split'] == split] for name, split in
              [('esc_train', 'train'), ('esc_val', 'validation'), ('esc_test', 'test')]}
    for key, folder in [('fsd_train', 'dev_subset'), ('fsd_val', 'dev_val_subset'),
                        ('fsd_eval', 'eval_subset')]:
        result[key] = load_group(FSD/folder, FSD/folder/'manifest.json')
    if any(r['original_split'] != 'train' for r in result['fsd_train']):
        raise ValueError('FSD train contains non-train audio')
    if any(r['original_split'] != 'val' for r in result['fsd_val']):
        raise ValueError('FSD validation contains non-validation audio')
    for i, (left_name, left) in enumerate(result.items()):
        for right_name, right in list(result.items())[i+1:]:
            try:
                assert_disjoint(left, right)
            except ValueError as exc:
                raise ValueError(f'{left_name}/{right_name}: {exc}') from exc
    return result


def checked_features(rows):
    values = []
    for row in rows:
        if hashlib.sha256(row['path'].read_bytes()).hexdigest() != row['sha256']:
            raise ValueError(f'audio checksum mismatch: {row["source_id"]}')
        values.append(features(row['path']))
    return values


def _wave(path, rate=16000):
    audio, original = sf.read(path, dtype='float32', always_2d=True)
    audio = audio.mean(axis=1)
    if original != rate:
        d = gcd(original, rate)
        audio = resample_poly(audio, rate//d, original//d).astype(np.float32)
    return audio


def augmented_bag(row, noise_path, seed):
    """Only training rows enter this deterministic volume/background augmentation."""
    rng = np.random.default_rng(seed)
    signal = _wave(row['path'])
    noise = _wave(noise_path)
    if not len(signal) or not len(noise):
        raise ValueError('empty augmentation source')
    noise = np.resize(noise, len(signal))
    gain = 10 ** (rng.uniform(-6, 6) / 20)
    signal = signal * gain
    noise_rms = float(np.sqrt(np.mean(noise ** 2)))
    if noise_rms > 1e-6:
        signal_rms = float(np.sqrt(np.mean(signal ** 2)))
        snr = 10 ** (rng.uniform(3, 15) / 20)
        signal += noise * (signal_rms / (noise_rms * snr + 1e-8))
    signal = np.clip(signal, -1, 1)
    result = []
    for start in range(0, len(signal), 16000*5):
        stream = io.BytesIO()
        sf.write(stream, signal[start:start+16000*5], 16000, format='WAV', subtype='FLOAT')
        stream.seek(0)
        result.append(logmel(stream))
    return torch.stack(result)


def scores(model, bags, mean, std):
    model.eval()
    with torch.inference_mode():
        return [float(model(((bag-mean)/std)).softmax(-1)[:, 1].max()) for bag in bags]


def metrics(rows, probs, threshold):
    return binary_metrics([r['expected'] for r in rows], probs, threshold)


def selected_threshold(rows, probabilities, baseline):
    feasible = []
    for threshold in np.linspace(.05, .95, 19):
        each = {key: metrics(rows[key], probabilities[key], threshold) for key in ('esc_val', 'fsd_val')}
        if all(each[key]['false_positive_rate'] <= baseline[key]['false_positive_rate'] + .05
               for key in each):
            feasible.append((sum(m['f1'] for m in each.values()) / 2, each, float(threshold)))
    if not feasible:
        return None
    score, each, threshold = max(feasible, key=lambda item: (item[0],
                                  sum(m['precision'] for m in item[1].values()) / 2, item[2]))
    return {'threshold': threshold, 'validation_mean_f1': score, 'validation': each}


def main():
    torch.set_num_threads(2)
    torch.manual_seed(20261011)
    rows = groups()
    bags = {key: checked_features(value) for key, value in rows.items()}
    print({key: len(value) for key, value in rows.items()}, flush=True)
    original = MODELS/'esc50_lstm.pt'
    saved = torch.load(original, map_location='cpu', weights_only=True)
    model = AudioClassifier('lstm')
    model.load_state_dict(saved['state_dict'])
    mean, std = saved['mean'], saved['std']
    baseline_prob = {key: scores(model, bags[key], mean, std) for key in ('esc_val', 'fsd_val')}
    base = {key: metrics(rows[key], baseline_prob[key], saved['threshold']) for key in baseline_prob}
    candidates = {'baseline': {'threshold': saved['threshold'], 'validation': base,
                                'validation_mean_f1': sum(m['f1'] for m in base.values())/2}}
    tuned = selected_threshold(rows, baseline_prob, base)
    if tuned:
        candidates['threshold_only'] = tuned

    train_rows = rows['esc_train'] + rows['fsd_train']
    train_bags = bags['esc_train'] + bags['fsd_train']
    noise = [r['path'] for r in rows['fsd_train'] if not r['expected']]
    if not noise:
        raise ValueError('no train-only background audio')
    # Add a single deterministic augmentation for each positive, preserving source grouping.
    augmented = [(r, augmented_bag(r, noise[i % len(noise)], 20261011+i))
                 for i, r in enumerate(train_rows) if r['expected']]
    train_bags += [bag for _, bag in augmented]
    train_y = torch.tensor([r['expected'] for r in train_rows] + [1]*len(augmented), dtype=torch.float32)
    normalized = [(bag-mean)/std for bag in train_bags]
    weight = ((train_y == 0).sum() / (train_y == 1).sum()).item()
    optimizer = torch.optim.Adam(model.parameters(), lr=.0001)
    best_aug_state = None
    best_aug_score = -1.0
    history = []
    for epoch in range(1, 5):
        model.train()
        order = torch.randperm(len(normalized)).tolist()
        for start in range(0, len(order), 16):
            batch = order[start:start+16]
            pieces = [normalized[i] for i in batch]
            optimizer.zero_grad()
            margin = bag_logits(model(torch.cat(pieces)), [len(p) for p in pieces])
            loss = F.binary_cross_entropy_with_logits(margin, train_y[batch],
                                                       pos_weight=torch.tensor(weight))
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5)
            optimizer.step()
        prob = {key: scores(model, bags[key], mean, std) for key in ('esc_val', 'fsd_val')}
        candidate = selected_threshold(rows, prob, base)
        history.append({'epoch': epoch, 'selection': candidate})
        if candidate and candidate['validation_mean_f1'] > best_aug_score:
            best_aug_score = candidate['validation_mean_f1']
            candidates['augmented_mil'] = {**candidate, 'epoch': epoch}
            best_aug_state = copy.deepcopy(model.state_dict())
        print(f'epoch {epoch}: {None if candidate is None else candidate["validation_mean_f1"]:.3f}'
              if candidate else f'epoch {epoch}: no feasible threshold', flush=True)

    chosen = max(candidates, key=lambda name: candidates[name]['validation_mean_f1'])
    if best_aug_state is not None:
        model.load_state_dict(best_aug_state)
    candidate_path = MODELS/'esc50_fsd_augmented_lstm.pt'
    if best_aug_state is not None:
        torch.save({**saved, 'state_dict': model.state_dict(),
                    'threshold': candidates[chosen]['threshold'],
                    'training_source': 'ESC+FSD train-only volume/background MIL'}, candidate_path)
    evals = {}
    runtime = {}
    for key in ('esc_test', 'fsd_eval'):
        unchanged = AudioClassifier('lstm')
        unchanged.load_state_dict(saved['state_dict'])
        begun = time.perf_counter()
        baseline_p = scores(unchanged, bags[key], mean, std)
        baseline_elapsed = time.perf_counter() - begun
        begun = time.perf_counter()
        augmented_p = scores(model, bags[key], mean, std) if best_aug_state is not None else None
        augmented_elapsed = time.perf_counter() - begun
        runtime[key] = {'baseline_total_s': baseline_elapsed,
                        'augmented_total_s': augmented_elapsed if augmented_p is not None else None,
                        'recordings': len(rows[key]), 'scope': 'feature tensors already loaded; model forward only'}
        evals[key] = {name: metrics(rows[key],
                     augmented_p if name == 'augmented_mil' else baseline_p,
                     candidate['threshold']) for name, candidate in candidates.items()
                     if name != 'augmented_mil' or augmented_p is not None}
    report = {'protocol': 'frozen ESC and FSD official dev/val candidate selection; previous inspected tests are development comparisons',
              'counts': {key: len(value) for key, value in rows.items()},
              'manifest_sha256': {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in
                                  [ESC/'manifest.json', FSD/'dev_subset/manifest.json',
                                   FSD/'dev_val_subset/manifest.json', FSD/'eval_subset/manifest.json']},
              'checkpoint_original_sha256': hashlib.sha256(original.read_bytes()).hexdigest(),
              'candidate_checkpoint': str(candidate_path) if chosen == 'augmented_mil' else None,
              'candidate_checkpoint_sha256': hashlib.sha256(candidate_path.read_bytes()).hexdigest()
                  if best_aug_state is not None else None,
              'selected': chosen, 'candidates': candidates, 'training_history': history,
              'evaluation': evals, 'runtime': runtime, 'promoted': False,
              'promotion_reason': 'No untouched household evaluation; selected augmentation regressed on inspected FSD eval',
              'limitations': ['Weak clip labels do not locate individual barks',
                              'Previously inspected ESC/FSD evaluation is not blind',
                              'Source IDs and hashes checked; transformed duplicate overlap remains possible',
                              'Balanced selected samples are not natural home prevalence']}
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'selected': chosen, 'validation': {k:v['validation_mean_f1'] for k,v in candidates.items()},
                      'evaluation': evals}), flush=True)


if __name__ == '__main__':
    main()
