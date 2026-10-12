"""Initial trajectory LSTM. Synthetic training is not real dog behavior validation."""
from pathlib import Path

import numpy as np
import torch
from torch import nn

from .motion import Observation

LABELS = ('still', 'moving', 'spinning', 'pacing')
FRAMES = 50
FPS = 5


class TrajectoryLSTM(nn.Module):
    def __init__(self, input_size=4):
        super().__init__()
        self.lstm = nn.LSTM(input_size, 48, batch_first=True)
        self.classifier = nn.Linear(48, len(LABELS))

    def forward(self, sequence):
        hidden, _ = self.lstm(sequence)
        return self.classifier(hidden[:, -1])


def features(coords, version=1):
    coords = np.asarray(coords, dtype=np.float32)
    centered = coords - coords[0]
    velocity = np.vstack([np.zeros((1, 2), dtype=np.float32), np.diff(coords, axis=0)]) * FPS
    basic = np.concatenate([centered, velocity], axis=1)
    if version == 1:
        return basic.astype(np.float32)
    if version != 2:
        raise ValueError('unsupported feature version')
    acceleration = np.vstack([np.zeros((1, 2)), np.diff(velocity, axis=0)]) * FPS
    speed = np.linalg.norm(velocity, axis=1, keepdims=True)
    turn = np.zeros((len(coords), 1))
    previous, following = velocity[:-1], velocity[1:]
    valid = (np.linalg.norm(previous, axis=1) > .01) & (np.linalg.norm(following, axis=1) > .01)
    cross = previous[:, 0]*following[:, 1] - previous[:, 1]*following[:, 0]
    turn[1:, 0] = np.where(valid, np.arctan2(cross, (previous*following).sum(1)) / np.pi, 0)
    return np.concatenate([basic, speed, acceleration, turn], axis=1).astype(np.float32)


class LSTMPredictor:
    def __init__(self, checkpoint: str | Path):
        saved = torch.load(checkpoint, map_location='cpu', weights_only=True)
        if saved['labels'] != list(LABELS) or saved['frames'] != FRAMES:
            raise ValueError('incompatible model metadata')
        self.feature_version = saved.get('feature_version', 1)
        if self.feature_version not in (1, 2):
            raise ValueError('unsupported checkpoint feature version')
        self.min_confidence = saved.get('min_confidence', .75)
        self.min_margin = saved.get('min_margin', .25)
        self.training_source = saved.get('training_source', 'synthetic_trajectories')
        self.model = TrajectoryLSTM(4 if self.feature_version == 1 else 8)
        self.model.load_state_dict(saved['state_dict'])
        self.model.eval()

    def predict(self, observations: list[Observation]):
        if not observations:
            return {'label': 'unknown', 'confidence': None, 'reason': 'no tracked observations'}
        # Fifty uniform model samples need temporal coverage, not fifty exact detector hits.
        # The tracker may now run faster than the 5 Hz inference grid.
        cutoff = observations[-1].t - 9.8
        observations = [o for o in observations if o.t >= cutoff - .05]
        if len(observations) < 40:
            return {'label': 'unknown', 'confidence': None, 'reason': 'less than 80% tracking coverage'}
        times = np.array([o.t for o in observations])
        coords = np.array([[o.cx, o.cy] for o in observations])
        if not np.isfinite(coords).all() or not np.isfinite(times).all():
            return {'label': 'unknown', 'confidence': None, 'reason': 'invalid coordinates'}
        if np.any(np.diff(times) <= 0) or np.max(np.diff(times)) > .65 or times[-1] - times[0] < 9.5:
            return {'label': 'unknown', 'confidence': None, 'reason': 'tracking gap or insufficient time'}
        target = np.linspace(times[-1] - 9.8, times[-1], FRAMES)
        if target[0] < times[0] - .05:
            return {'label': 'unknown', 'confidence': None, 'reason': 'window not covered'}
        covered_samples = int((np.min(np.abs(times[:, None] - target[None, :]), axis=0) <= .12).sum())
        if covered_samples < 40:
            return {'label': 'unknown', 'confidence': None, 'reason': 'less than 80% tracking coverage'}
        sampled = np.column_stack([np.interp(target, times, coords[:, i]) for i in range(2)])
        if np.max(np.linalg.norm(np.diff(sampled, axis=0), axis=1)) > .15:
            return {'label': 'unknown', 'confidence': None, 'reason': 'implausible track jump; identity/camera check required'}
        with torch.inference_mode():
            probabilities = self.model(torch.from_numpy(features(sampled, self.feature_version)[None])).softmax(-1)[0]
        index = int(probabilities.argmax())
        top = probabilities.topk(2).values
        uncertain = float(top[0]) < self.min_confidence or float(top[0]-top[1]) < self.min_margin
        return {'label': 'unknown' if uncertain else LABELS[index], 'confidence': float(probabilities[index]),
                'probabilities': dict(zip(LABELS, probabilities.tolist())),
                'training_source': self.training_source, 'feature_version': self.feature_version,
                'observed_samples': len(observations), 'model_samples': FRAMES,
                'interpolated_missing_samples': FRAMES-covered_samples,
                'reason': 'low confidence or ambiguous classes' if uncertain else
                          'trajectory estimate; real behavior classification accuracy unverified'}
