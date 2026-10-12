"""Supervised three-second LSTM for A2D walking/running versus eating.

Publisher test clips remain untouched until checkpoint and operating threshold
have been selected using only train/validation clips.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from pet_monitor.lstm import features
from pet_monitor.short_motion import FRAMES, LABELS, ShortMotionLSTM
from scripts.prepare_a2d import ROOT, sha256


def confusion(expected, positive):
    expected = np.asarray(expected).astype(bool)
    positive = np.asarray(positive).astype(bool)
    tp, fp = int((expected & positive).sum()), int((~expected & positive).sum())
    fn, tn = int((expected & ~positive).sum()), int((~expected & ~positive).sum())
    return {'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
            'precision': tp/(tp+fp) if tp+fp else None,
            'recall': tp/(tp+fn) if tp+fn else None,
            'specificity': tn/(tn+fp) if tn+fp else None,
            'balanced_accuracy': ((tp/(tp+fn) + tn/(tn+fp))/2) if tp+fn and tn+fp else None}


def probabilities(model, x):
    model.eval()
    with torch.inference_mode():
        return model(x).softmax(-1)[:, 1].cpu().numpy()


def choose_threshold(y, scores, minimum_precision=.8):
    options = []
    for threshold in sorted(set(float(x) for x in scores)):
        metrics = confusion(y, scores >= threshold)
        if metrics['precision'] is not None and metrics['precision'] >= minimum_precision and metrics['tp'] >= 2:
            options.append((metrics['recall'], metrics['precision'], threshold))
    return float(max(options)[2]) if options else 1.0


def run(output, epochs, stem='short'):
    if not stem.isidentifier():
        raise ValueError('invalid A2D data stem')
    torch.set_num_threads(2)
    torch.manual_seed(20261011)
    path = ROOT / f'{stem}_trajectories.npz'
    manifest = json.loads((ROOT / f'{stem}_manifest.json').read_text(encoding='utf-8'))
    if sha256(path) != manifest['data_sha256']:
        raise ValueError('A2D trajectories differ from reviewed manifest')
    saved = np.load(path, allow_pickle=False)
    coords, y, splits, ids = saved['coords'], saved['labels'], saved['splits'], saved['ids']
    if coords.ndim != 3 or coords.shape[1:] != (FRAMES, 2) or not np.isfinite(coords).all():
        raise ValueError('invalid A2D feature shape')
    if len(set(ids.tolist())) != len(ids) or set(splits.tolist()) != {'train', 'validation', 'test'}:
        raise ValueError('missing split or duplicate clip ID')
    x = torch.from_numpy(np.stack([features(row, 2) for row in coords]))
    split_indices = {name: np.flatnonzero(splits == name) for name in ('train', 'validation', 'test')}
    if any(len(np.unique(y[index])) != 2 for index in split_indices.values()):
        raise ValueError('each split needs both publisher action groups')
    model = ShortMotionLSTM()
    train = split_indices['train']; val = split_indices['validation']; test = split_indices['test']
    counts = np.bincount(y[train], minlength=2)
    weights = torch.tensor(len(train)/(2*counts), dtype=torch.float32)
    loss_fn = nn.CrossEntropyLoss(weight=weights)
    optimizer = torch.optim.AdamW(model.parameters(), lr=.002, weight_decay=.01)
    loader = DataLoader(TensorDataset(x[train], torch.from_numpy(y[train]).long()), batch_size=32,
                        shuffle=True, generator=torch.Generator().manual_seed(20261011))
    best_score, best_loss, best_state = -1, float('inf'), None
    history = []
    for epoch in range(epochs):
        model.train()
        for batch_x, batch_y in loader:
            optimizer.zero_grad()
            loss = loss_fn(model(batch_x), batch_y)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
        scores = probabilities(model, x[val])
        metrics = confusion(y[val], scores >= .5)
        with torch.inference_mode():
            val_loss = float(loss_fn(model(x[val]), torch.from_numpy(y[val]).long()))
        balanced = metrics['balanced_accuracy']
        history.append({'epoch': epoch+1, 'validation_balanced_accuracy': balanced, 'validation_loss': val_loss})
        if balanced > best_score or (balanced == best_score and val_loss < best_loss):
            best_score, best_loss = balanced, val_loss
            best_state = {key: value.detach().clone() for key, value in model.state_dict().items()}
    model.load_state_dict(best_state)
    val_scores = probabilities(model, x[val])
    threshold = choose_threshold(y[val], val_scores)
    test_scores = probabilities(model, x[test])
    output.mkdir(parents=True, exist_ok=True)
    checkpoint = output / 'a2d_short_lstm.pt'
    torch.save({'state_dict': best_state, 'labels': list(LABELS), 'frames': FRAMES,
                'locomotion_threshold': threshold, 'training_source': 'A2D single-action dog videos'}, checkpoint)
    path_distance = np.linalg.norm(np.diff(coords, axis=1), axis=2).sum(axis=1)
    baseline_threshold = max((float(v) for v in np.unique(path_distance[val])),
                             key=lambda cut: (confusion(y[val], path_distance[val] >= cut)['balanced_accuracy'], -cut))
    report = {'task': 'A2D dog walking/running versus eating; not still/spinning/pacing accuracy',
              'source_data_sha256': manifest['data_sha256'], 'checkpoint_sha256': sha256(checkpoint),
              'split_counts': {name: {'eating': int((y[index] == 0).sum()),
                                      'locomotion': int((y[index] == 1).sum())} for name, index in split_indices.items()},
              'selection': 'best validation balanced accuracy at 0.5, then validation precision >= 0.8 operating threshold',
              'threshold': threshold, 'validation': confusion(y[val], val_scores >= threshold),
              'test': confusion(y[test], test_scores >= threshold),
              'test_at_0_5': confusion(y[test], test_scores >= .5),
              'baseline': {'feature': 'three-second box-center path length', 'threshold_from_validation': baseline_threshold,
                           'validation': confusion(y[val], path_distance[val] >= baseline_threshold),
                           'test': confusion(y[test], path_distance[test] >= baseline_threshold)},
              'heldout_predictions': [{'id': str(ids[i]), 'expected': LABELS[y[i]], 'locomotion_probability': float(score),
                                       'positive': bool(score >= threshold)} for i, score in zip(test, test_scores)],
              'history': history,
              'limits': ['A2D action labels are clip-level and primary actor/action only',
                         'dog identity across YouTube videos is unknown',
                         'eating is not synonymous with still', 'camera motion is not compensated']}
    (output / 'evaluation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'split_counts': report['split_counts'], 'threshold': threshold,
                      'validation': report['validation'], 'test': report['test'],
                      'baseline_test': report['baseline']['test']}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('artifacts/a2d_short'))
    parser.add_argument('--epochs', type=int, default=60)
    parser.add_argument('--stem', default='short')
    args = parser.parse_args()
    run(args.output, args.epochs, args.stem)
