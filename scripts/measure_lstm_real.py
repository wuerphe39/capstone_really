"""Frozen v1/v2 representations: real motion forecasting + pending class references.

Forecast error is measurable from recorded coordinates. It must never be called
four-class behavioral accuracy. No operational checkpoint is changed here.
"""
import hashlib
import argparse
import json
from pathlib import Path

import numpy as np
import torch

from pet_monitor.lstm import FPS, FRAMES, LSTMPredictor, features

OUTPUT = Path('artifacts/real_evaluation')
MODELS = {'v1': Path('artifacts/lstm/trajectory_lstm_v1_backup.pt'),
          'v2': Path('artifacts/lstm/trajectory_lstm.pt')}


def ridge_fit(x, y, alpha):
    mean, scale = x.mean(0), x.std(0)
    scale = np.maximum(scale, 1e-6)
    design = np.column_stack([(x-mean)/scale, np.ones(len(x))])
    penalty = np.eye(design.shape[1])*alpha
    penalty[-1, -1] = 0
    weights = np.linalg.solve(design.T@design + penalty, design.T@y)
    return mean, scale, weights


def ridge_predict(x, fitted):
    mean, scale, weights = fitted
    return np.column_stack([(x-mean)/scale, np.ones(len(x))]) @ weights


def clustered_change_ci(old, new, groups, seed=20261011):
    identities = sorted(set(groups))
    pairs = np.array([[old[groups == group].mean(), new[groups == group].mean()] for group in identities])
    rng = np.random.default_rng(seed)
    sampled = pairs[rng.integers(0, len(pairs), size=(10000, len(pairs)))].mean(axis=1)
    changes = 100*(1-sampled[:, 1]/sampled[:, 0])
    return {'unit': 'recording_family', 'families': len(identities),
            'equal_family_error_reduction_percent': float(100*(1-pairs[:, 1].mean()/pairs[:, 0].mean())),
            'percentile_95_ci': np.percentile(changes, [2.5, 97.5]).tolist(),
            'resamples': 10000, 'seed': seed}


def main(dataset_path=None, candidate=None, output=OUTPUT):
    torch.set_num_threads(2)
    output.mkdir(parents=True, exist_ok=True)
    path = dataset_path or Path('artifacts/datasets/ai4animation/windows.npz')
    manifest = json.loads(path.with_name('manifest.json').read_text(encoding='utf-8'))
    data_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    if data_hash != manifest['windows_sha256']:
        raise ValueError('dataset checksum mismatch')
    saved = np.load(path, allow_pickle=False)
    coords, splits, groups = saved['coords'], saved['splits'], saved['groups']
    identities = {split: set(groups[splits == split]) for split in ['train', 'validation', 'test']}
    if any(identities[a] & identities[b] for a, b in [('train', 'validation'), ('train', 'test'), ('validation', 'test')]):
        raise ValueError('recording split leakage')
    projection_scale = manifest.get('projection_scale', 1000)
    projected = (coords-coords[:, :1])/projection_scale + .5
    horizon = FPS
    # Both frozen models see exactly the same actual coordinate windows and targets.
    persistence = projected[:, :-horizon] + np.concatenate(
        [np.zeros_like(projected[:, :1]), np.diff(projected, axis=1)], axis=1)[:, :-horizon]*horizon
    target = projected[:, horizon:]
    residual = target-persistence
    errors, model_reports = {}, {}
    models = dict(MODELS)
    if candidate:
        models['v3'] = candidate
    for name, checkpoint in models.items():
        predictor = LSTMPredictor(checkpoint)
        inputs = torch.from_numpy(np.stack([features(c, predictor.feature_version) for c in projected]))
        with torch.inference_mode():
            hidden = predictor.model.lstm(inputs[:, :-horizon])[0].numpy().astype(np.float64)
        x, y = hidden[splits == 'train'].reshape(-1, 48), residual[splits == 'train'].reshape(-1, 2)
        candidates = []
        for alpha in [.01, .1, 1., 10., 100.]:
            fitted = ridge_fit(x, y, alpha)
            predicted = ridge_predict(hidden[splits == 'validation'].reshape(-1, 48), fitted)
            error = float(np.mean((predicted-residual[splits == 'validation'].reshape(-1, 2))**2))
            candidates.append((error, alpha, fitted))
        validation_mse, alpha, fitted = min(candidates, key=lambda item: item[0])
        prediction = persistence[splits == 'test'] + ridge_predict(
            hidden[splits == 'test'].reshape(-1, 48), fitted).reshape(-1, FRAMES-horizon, 2)
        errors[name] = np.mean((prediction-target[splits == 'test'])**2, axis=(1, 2))
        np.savez_compressed(output / f'{name}_forecast_readout.npz', mean=fitted[0], scale=fitted[1], weights=fitted[2])
        model_reports[name] = {'checkpoint': str(checkpoint),
                              'checkpoint_sha256': hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
                              'feature_version': predictor.feature_version,
                              'selected_ridge_alpha': alpha, 'validation_mse': validation_mse,
                              'test_mse': float(errors[name].mean()),
                              'test_rmse': float(np.sqrt(errors[name].mean()))}
    baseline = np.mean((persistence[splits == 'test']-target[splits == 'test'])**2, axis=(1, 2))
    test_groups = groups[splits == 'test']
    comparisons = {'v2_vs_v1': {'error_reduction_percent': float(100*(1-errors['v2'].mean()/errors['v1'].mean())),
                                'bootstrap': clustered_change_ci(errors['v1'], errors['v2'], test_groups)}}
    if candidate:
        comparisons['v3_vs_v2'] = {'error_reduction_percent': float(100*(1-errors['v3'].mean()/errors['v2'].mean())),
                                   'bootstrap': clustered_change_ci(errors['v2'], errors['v3'], test_groups)}
    report = {'task': 'one-second root-coordinate forecasting using frozen classification encoders + ridge readout',
              'behavior_classification_accuracy': None, 'dataset_sha256': data_hash,
              'dataset': manifest['dataset'], 'projection_scale': projection_scale, 'comparisons': comparisons,
              'models': model_reports, 'constant_velocity_test_mse': float(baseline.mean()),
              'window_weighted_error_reduction_percent': float(100*(1-errors['v2'].mean()/errors['v1'].mean())),
              'paired_cluster_bootstrap': clustered_change_ci(errors['v1'], errors['v2'], test_groups),
              'split_windows': {split: int(sum(splits == split)) for split in identities},
              'split_groups': {split: sorted(values) for split, values in identities.items()},
              'windows': [{'index': int(i), 'group': str(group), 'v1_mse': float(a), 'v2_mse': float(b),
                           'constant_velocity_mse': float(c)}
                          for i, group, a, b, c in zip(np.where(splits == 'test')[0], test_groups,
                                                      errors['v1'], errors['v2'], baseline)],
              'limitations': ['root-coordinate probe, not camera behavior accuracy',
                              'automated pose fits are not independent ground truth' if 'InterPet' in manifest['dataset'] else 'one captured dog',
                              'few held-out groups; bootstrap interval is exploratory',
                              'development dataset; separate future behavioral benchmark required',
                              'ridge readouts fitted for this probe; operational behavior classifiers unchanged',
                              'no independent human four-class behavior references']}
    if candidate:
        for row, error in zip(report['windows'], errors['v3']):
            row['v3_mse'] = float(error)
    (output / 'paired_forecasting.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    # A review template does not invent reference labels from model predictions.
    template = {'dataset_sha256': data_hash, 'projection_scale': projection_scale,
                'annotation_policy': 'reference expected/reviewer/provenance must be supplied independently of model outputs',
                'samples': [{'id': f'mocap-{i}', 'group': str(groups[i]), 'expected': None,
                             'reviewer': None, 'label_provenance': None,
                             'observations': [{'t': j/FPS, 'cx': float(c[0]), 'cy': float(c[1])}
                                              for j, c in enumerate(projected[i])]}
                            for i in np.where(splits == 'test')[0]]}
    template_path = output / 'reference_template.json'
    if not template_path.exists():
        template_path.write_text(json.dumps(template, indent=2), encoding='utf-8')
    print(json.dumps({'models': model_reports,
                      'error_reduction_percent': report['window_weighted_error_reduction_percent'],
                      'bootstrap': report['paired_cluster_bootstrap'],
                      'comparisons': comparisons,
                      'behavior_classification_accuracy': None}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', type=Path)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args(); main(args.dataset, args.candidate, args.output)
