"""Compare fixed LSTM, YAMNet scores, pooled embeddings, and temporal LSTM.

The official FSD eval and ESC test sets were previously inspected, so the
final comparison is a development audit, never a blind accuracy estimate.
"""
import copy
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from pet_monitor.audio_lstm import AudioPredictor, binary_metrics
from pet_monitor.yamnet_lstm import YamnetEmbeddingClassifier


ROOT = Path('artifacts/yamnet_bark_experiment')
OLD_MODEL = Path('artifacts/audio_lstm/esc50_lstm.pt')
SEED = 20261012
EPOCHS = 10
BATCH_SIZE = 16


def load_rows():
    manifest_path = ROOT/'manifest.json'
    extraction = json.loads((ROOT/'extraction.json').read_text(encoding='utf-8'))
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != extraction['manifest_sha256']:
        raise ValueError('manifest changed after YAMNet extraction')
    payload = json.loads(manifest_path.read_text(encoding='utf-8'))
    result = {}
    for split, rows in payload['rows'].items():
        result[split] = []
        for row in rows:
            with np.load(ROOT/'features'/(row['sha256']+'.npz')) as data:
                if (int(data['version']) != 3 or data['embeddings'].shape[1] != 1024 or
                        str(data['model_sha256']) != extraction['model_sha256']):
                    raise ValueError(f'incompatible YAMNet features: {row["id"]}')
                lengths = data['lengths'].astype(int)
                pieces = np.split(data['embeddings'].astype(np.float32),
                                  np.cumsum(lengths)[:-1])
                if any(len(part) != length for part, length in zip(pieces, lengths)):
                    raise ValueError('embedding window lengths mismatch')
                result[split].append({**row, 'pieces': pieces,
                                      'yamnet_bark': float(data['scores'][:, 0].max())})
    return result, extraction


def normalize_and_pad(rows):
    train_patches = np.concatenate([part for row in rows['train'] for part in row['pieces']])
    mean = train_patches.mean(0)
    std = np.maximum(train_patches.std(0), .05)
    max_patches = max(len(part) for split in rows.values() for row in split for part in row['pieces'])
    for split in rows.values():
        for row in split:
            normalized = [(part-mean)/std for part in row['pieces']]
            row['x'] = torch.from_numpy(np.stack([
                np.pad(part, ((0, max_patches-len(part)), (0, 0))) for part in normalized]))
            row['lengths'] = torch.tensor([len(part) for part in normalized], dtype=torch.long)
    return mean, std, max_patches


def predict(model, rows, reverse=False):
    model.eval()
    start = time.perf_counter()
    outputs = []
    with torch.inference_mode():
        for offset in range(0, len(rows), BATCH_SIZE):
            group = rows[offset:offset+BATCH_SIZE]
            x = torch.cat([row['x'] for row in group])
            lengths = torch.cat([row['lengths'] for row in group])
            if reverse:
                x = x.clone()
                for i, length in enumerate(lengths):
                    x[i, :length] = x[i, :length].flip(0)
            margins = model(x, lengths)
            position = 0
            for row in group:
                count = len(row['x'])
                outputs.append(float(torch.sigmoid(margins[position:position+count].max())))
                position += count
    return outputs, time.perf_counter()-start


def train(kind, rows, baseline_fpr):
    torch.manual_seed(SEED)
    model = YamnetEmbeddingClassifier(kind)
    optimizer = torch.optim.AdamW(model.parameters(), lr=.0005, weight_decay=.01)
    positives = sum(row['label'] for row in rows['train'])
    negatives = len(rows['train'])-positives
    pos_weight = torch.tensor(negatives/positives)
    best = None
    history = []
    for epoch in range(1, EPOCHS+1):
        model.train()
        order = torch.randperm(len(rows['train'])).tolist()
        losses = []
        for offset in range(0, len(order), BATCH_SIZE):
            chosen = [rows['train'][i] for i in order[offset:offset+BATCH_SIZE]]
            x = torch.cat([row['x'] for row in chosen])
            lengths = torch.cat([row['lengths'] for row in chosen])
            margins = model(x, lengths)
            position = 0
            bag = []
            for row in chosen:
                count = len(row['x'])
                bag.append(margins[position:position+count].max())
                position += count
            labels = torch.tensor([row['label'] for row in chosen], dtype=torch.float32)
            loss = F.binary_cross_entropy_with_logits(torch.stack(bag), labels, pos_weight=pos_weight)
            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 5)
            optimizer.step()
            losses.append(float(loss.detach()))
        scores, _ = predict(model, rows['val'])
        choice = tune(rows['val'], scores, baseline_fpr)
        history.append({'epoch': epoch, 'loss': float(np.mean(losses)), 'validation': choice})
        if choice and (best is None or (choice['f1'], -choice['false_positive_rate']) > best['rank']):
            best = {'rank': (choice['f1'], -choice['false_positive_rate']),
                    'epoch': epoch, 'state': copy.deepcopy(model.state_dict()),
                    'validation': choice}
        print(f'{kind} epoch {epoch}: loss={np.mean(losses):.3f} '
              f'val_f1={choice["f1"] if choice else None}', flush=True)
    if best is None:
        raise ValueError(f'{kind}: no validation threshold meets false-positive limit')
    model.load_state_dict(best['state'])
    return model, best, history


def measure(rows, scores, threshold):
    return binary_metrics([r['label'] for r in rows], scores, threshold)


def tune(rows, scores, max_fpr):
    candidates = []
    for threshold in np.arange(.05, .96, .05):
        metrics = measure(rows, scores, threshold)
        if metrics['false_positive_rate'] <= max_fpr:
            candidates.append(metrics)
    if not candidates:
        return None
    return max(candidates, key=lambda m: (m['f1'], m['precision'], m['threshold']))


def old_scores(rows):
    predictor = AudioPredictor(OLD_MODEL)
    start = time.perf_counter()
    scores = [predictor.predict(row['path'])['dog_score'] for row in rows]
    return scores, time.perf_counter()-start, predictor.threshold


def overlap(rows, old, yamnet, old_threshold, yamnet_threshold):
    counts = {'both_find': 0, 'yamnet_only': 0, 'old_only': 0, 'both_miss': 0}
    for row, a, b in zip(rows, old, yamnet):
        if not row['label']:
            continue
        key = ('both_find' if a >= old_threshold and b >= yamnet_threshold else
               'yamnet_only' if b >= yamnet_threshold else
               'old_only' if a >= old_threshold else 'both_miss')
        counts[key] += 1
    return counts


def main():
    torch.set_num_threads(2)
    np.random.seed(SEED)
    rows, extraction = load_rows()
    mean, std, max_patches = normalize_and_pad(rows)
    old_val, old_val_s, old_threshold = old_scores(rows['val'])
    old_eval, old_eval_s, _ = old_scores(rows['eval'])
    old_fixed_val = measure(rows['val'], old_val, old_threshold)
    max_fpr = min(.10, old_fixed_val['false_positive_rate']+.05)
    old_tuned = tune(rows['val'], old_val, max_fpr)
    yamnet_val = [r['yamnet_bark'] for r in rows['val']]
    yamnet_eval = [r['yamnet_bark'] for r in rows['eval']]
    yamnet_choice = tune(rows['val'], yamnet_val, max_fpr)
    if yamnet_choice is None:
        raise ValueError('YAMNet direct scores cannot meet validation false-positive limit')
    comparison = {
        'old_lstm_fixed': {'threshold': old_threshold, 'val': old_fixed_val,
                           'eval': measure(rows['eval'], old_eval, old_threshold),
                           'eval_inference_s': old_eval_s},
        'old_lstm_tuned': {'threshold': old_tuned['threshold'] if old_tuned else None,
                           'val': old_tuned, 'eval': measure(rows['eval'], old_eval,
                           old_tuned['threshold']) if old_tuned else None},
        'yamnet_bark': {'threshold': yamnet_choice['threshold'], 'val': yamnet_choice,
                        'eval': measure(rows['eval'], yamnet_eval, yamnet_choice['threshold'])},
    }
    states = {}
    for kind in ('pooled', 'lstm'):
        model, best, history = train(kind, rows, max_fpr)
        eval_scores, elapsed = predict(model, rows['eval'])
        name = 'yamnet_embedding_'+kind
        comparison[name] = {'threshold': best['validation']['threshold'],
                            'selected_epoch': best['epoch'], 'val': best['validation'],
                            'eval': measure(rows['eval'], eval_scores, best['validation']['threshold']),
                            'eval_inference_s': elapsed, 'history': history}
        if kind == 'lstm':
            reversed_scores, _ = predict(model, rows['eval'], reverse=True)
            comparison[name]['eval_reversed_patches'] = measure(
                rows['eval'], reversed_scores, best['validation']['threshold'])
        states[kind] = (model, best)
    or_val = [max(int(a >= old_threshold), int(b >= yamnet_choice['threshold']))
              for a, b in zip(old_val, yamnet_val)]
    or_eval = [max(int(a >= old_threshold), int(b >= yamnet_choice['threshold']))
               for a, b in zip(old_eval, yamnet_eval)]
    comparison['parallel_or'] = {'val': measure(rows['val'], or_val, .5),
                                 'eval': measure(rows['eval'], or_eval, .5)}
    report = {
        'task': 'explicit FSD50K Bark vs FSD non-Dog and sampled ESC non-Dog',
        'counts': {split: {'total': len(items), 'bark': sum(r['label'] for r in items)}
                   for split, items in rows.items()},
        'model_source': extraction, 'baseline_checkpoint_sha256': hashlib.sha256(OLD_MODEL.read_bytes()).hexdigest(),
        'selection_rule': f'validation F1, FPR <= {max_fpr:.3f}; no eval threshold tuning',
        'comparison': comparison,
        'positive_error_overlap': overlap(rows['eval'], old_eval, yamnet_eval,
                                          old_threshold, yamnet_choice['threshold']),
        'limitations': ['FSD Bark labels are clip-level, not exact onset labels',
                        'FSD/ESC eval files were previously inspected, so this is not blind testing',
                        'YAMNet pretraining on AudioSet may overlap Freesound-derived audio; overlap unverified',
                        'selected balanced negatives do not represent natural home prevalence'],
        'promoted': False,
    }
    ROOT.mkdir(parents=True, exist_ok=True)
    for kind, (model, best) in states.items():
        torch.save({'kind': kind, 'state_dict': model.state_dict(),
                    'mean': torch.from_numpy(mean), 'std': torch.from_numpy(std),
                    'max_patches': max_patches, 'threshold': best['validation']['threshold'],
                    'yamnet_model_sha256': extraction['model_sha256'],
                    'training_scope': 'explicit FSD Bark + non-Dog clips only'},
                   ROOT/f'yamnet_embedding_{kind}.pt')
    (ROOT/'comparison.json').write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                        encoding='utf-8')
    print(json.dumps({'counts': report['counts'],
                      'eval': {k: v['eval'] for k, v in comparison.items()},
                      'overlap': report['positive_error_overlap']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
