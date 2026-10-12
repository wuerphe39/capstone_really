"""Reproducible trajectory-level train/validation/test split using disjoint seeds."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from pet_monitor.lstm import FPS, FRAMES, LABELS, TrajectoryLSTM, features
from pet_monitor.simulator import make_trajectory


def dataset(per_class, seed, version=2):
    rng = np.random.default_rng(seed)
    x, y = [], []
    for label, kind in enumerate(LABELS):
        for _ in range(per_class):
            speed = rng.uniform(.7, 1.3)
            obs = make_trajectory(kind, 10 / speed, fps=FPS * speed, seed=int(rng.integers(0, 2**31)))[:FRAMES]
            coords = np.array([[o.cx, o.cy] for o in obs])
            if len(coords) < FRAMES:
                raise ValueError('generator produced too few frames')
            angle = rng.uniform(-np.pi, np.pi)
            rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
            coords = (coords - .5) @ rotation * rng.uniform(.6, 1.2) + rng.uniform(.35, .65, 2)
            coords += rng.normal(0, rng.uniform(.001, .006), coords.shape)
            x.append(features(coords, version)); y.append(label)
    return TensorDataset(torch.from_numpy(np.stack(x)), torch.tensor(y))


def pretrain(model, path, output, epochs=60):
    """Next-step prediction on actual mocap, with no invented class labels."""
    saved = np.load(path, allow_pickle=False)
    manifest = json.loads(path.with_name('manifest.json').read_text(encoding='utf-8'))
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest['windows_sha256']:
        raise ValueError('pretraining data differs from reviewed manifest')
    coords, splits, groups = saved['coords'], saved['splits'], saved['groups']
    group_sets = {split: set(groups[splits == split]) for split in ['train', 'validation', 'test']}
    if not np.isfinite(coords).all() or coords.shape[1:] != (FRAMES, 2) or any(not s for s in group_sets.values()):
        raise ValueError('invalid or empty pretraining split')
    if any(group_sets[a] & group_sets[b] for a, b in [('train', 'validation'), ('train', 'test'), ('validation', 'test')]):
        raise ValueError('recording-family split leakage')
    projection_scale = manifest.get('projection_scale', 1000)
    projected = (coords-coords[:, :1]) / projection_scale + .5
    tensors = {split: torch.from_numpy(np.stack([features(c, 2) for c in projected[splits == split]]))
               for split in group_sets}
    head = nn.Linear(48, 4)
    nn.init.zeros_(head.weight); nn.init.zeros_(head.bias)
    optimizer = torch.optim.Adam(list(model.lstm.parameters()) + list(head.parameters()), lr=.002)
    loss_fn = nn.MSELoss()
    horizon = 5  # One second at the original 5Hz sample rate.
    best, best_state, history = float('inf'), None, []
    def targets(x):
        target = x[:, horizon:, :4]
        persistence = x[:, :-horizon, :4].clone()
        persistence[:, :, :2] += persistence[:, :, 2:] * (horizon / FPS)
        return target, persistence
    def score(split):
        with torch.inference_mode():
            x = tensors[split]
            h, _ = model.lstm(x[:, :-horizon])
            target, persistence = targets(x)
            return {'next_step_mse': float(loss_fn(persistence + head(h), target)),
                    'constant_velocity_mse': float(loss_fn(persistence, target))}
    initial = score('validation')
    best = initial['next_step_mse']
    best_state = ({k: v.detach().clone() for k, v in model.lstm.state_dict().items()},
                  {k: v.detach().clone() for k, v in head.state_dict().items()})
    loader = DataLoader(TensorDataset(tensors['train']), batch_size=32, shuffle=True,
                        generator=torch.Generator().manual_seed(42))
    for epoch in range(epochs):
        model.train(); head.train()
        for (x,) in loader:
            optimizer.zero_grad()
            h, _ = model.lstm(x[:, :-horizon])
            target, persistence = targets(x)
            loss = loss_fn(persistence + head(h), target); loss.backward()
            nn.utils.clip_grad_norm_(model.lstm.parameters(), 1.0)
            optimizer.step()
        model.eval(); head.eval()
        result = score('validation'); history.append({'epoch': epoch+1, **result})
        if result['next_step_mse'] < best:
            best = result['next_step_mse']
            best_state = ({k: v.detach().clone() for k, v in model.lstm.state_dict().items()},
                          {k: v.detach().clone() for k, v in head.state_dict().items()})
    model.lstm.load_state_dict(best_state[0]); head.load_state_dict(best_state[1])
    output.mkdir(parents=True, exist_ok=True)
    torch.save({'lstm': best_state[0], 'residual_head': best_state[1], 'feature_version': 2,
                'horizon_samples': horizon, 'projection_scale': projection_scale}, output / 'mocap_forecaster.pt')
    return {'source': manifest['dataset'], 'role': 'self_supervised_pretraining',
            'behavior_labels': None, 'projection_scale': projection_scale, 'horizon_seconds': horizon/FPS,
            'archive_sha256': manifest['archive_sha256'], 'windows_sha256': manifest['windows_sha256'],
            'evaluation_status': ('dog-separated development evaluation; test not used for checkpoint selection' if 'InterPet' in manifest['dataset']
                                  else 'development recording split; reused during exploratory forecast-task design; not a blind benchmark'),
            'initial_validation': initial,
            'validation': score('validation'), 'test': score('test'),
            'windows': {split: len(x) for split, x in tensors.items()},
            'groups': {split: sorted(values) for split, values in group_sets.items()}, 'history': history}


def evaluate(model, data):
    with torch.inference_mode():
        x, y = data.tensors
        predicted = model(x).argmax(-1)
    matrix = [[int(((y == i) & (predicted == j)).sum()) for j in range(4)] for i in range(4)]
    return {'accuracy': float((y == predicted).float().mean()), 'confusion_matrix': matrix}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--epochs', type=int, default=45)
    parser.add_argument('--output', type=Path, default=Path('artifacts/lstm'))
    parser.add_argument('--pretrain-data', type=Path)
    args = parser.parse_args()
    torch.set_num_threads(2)
    torch.manual_seed(42)
    train, validation, test = dataset(400, 11), dataset(100, 22), dataset(100, 33)
    model = TrajectoryLSTM(input_size=8)
    pretraining = pretrain(model, args.pretrain_data, args.output) if args.pretrain_data else None
    optimizer = torch.optim.Adam(model.parameters(), lr=.003)
    loss_fn = nn.CrossEntropyLoss()
    loader = DataLoader(train, batch_size=64, shuffle=True, generator=torch.Generator().manual_seed(42))
    best, best_state, history = -1, None, []
    for epoch in range(args.epochs):
        model.train()
        for x, y in loader:
            optimizer.zero_grad(); loss = loss_fn(model(x), y); loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0); optimizer.step()
        model.eval()
        result = evaluate(model, validation)
        history.append({'epoch': epoch + 1, 'validation_accuracy': result['accuracy']})
        if result['accuracy'] > best:
            best = result['accuracy']
            best_state = {name: value.detach().clone() for name, value in model.state_dict().items()}
        if epoch % 10 == 0 or epoch == args.epochs - 1:
            print(history[-1], flush=True)
    model.load_state_dict(best_state)
    args.output.mkdir(parents=True, exist_ok=True)
    torch.save({'state_dict': best_state, 'labels': list(LABELS), 'frames': FRAMES,
                'feature_version': 2, 'min_confidence': .75, 'min_margin': .25,
                'training_source': ('interpet_pose_pretrain_synthetic_classification' if pretraining and 'InterPet' in pretraining['source']
                                    else 'real_mocap_pretrain_synthetic_classification' if pretraining else 'synthetic_trajectories')}, args.output / 'trajectory_lstm.pt')
    report = {'training_source': ('interpet_pose_pretrain_synthetic_classification' if pretraining and 'InterPet' in pretraining['source']
                                 else 'real_mocap_pretrain_synthetic_classification' if pretraining else 'synthetic_trajectories'),
              'pretraining': pretraining, 'real_behavior_accuracy': None, 'feature_version': 2,
              'unknown_thresholds': {'confidence': .75, 'margin': .25,
                                     'status': 'provisional; real OOD calibration required'},
              'split_seeds': {'train': 11, 'validation': 22, 'test': 33},
              'split_sizes': {'train': len(train), 'validation': len(validation), 'test': len(test)},
              'labels': list(LABELS), 'frames': FRAMES, 'fps': FPS, 'epochs': args.epochs,
              'validation_best': best, 'test': evaluate(model, test), 'history': history,
              'limitations': ['behavior classes trained on synthetic trajectories', 'camera motion not compensated',
                              'no real dog behavior labels', 'mocap projection is not a camera track']}
    (args.output / 'evaluation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'validation_best': best, 'test': report['test']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
