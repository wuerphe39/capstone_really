"""Three-second A2D dog locomotion versus eating research model.

This task is narrower than the existing four-class trajectory LSTM. An
"eating" prediction must never be converted into "still".
"""
from pathlib import Path

import numpy as np
import torch
from torch import nn

from .lstm import FPS, features

LABELS = ('eating', 'locomotion')
FRAMES = 15


class ShortMotionLSTM(nn.Module):
    def __init__(self):
        super().__init__()
        self.lstm = nn.LSTM(8, 32, batch_first=True)
        self.classifier = nn.Linear(32, 2)

    def forward(self, x):
        hidden, _ = self.lstm(x)
        return self.classifier(hidden[:, -1])


class ShortMotionPredictor:
    def __init__(self, checkpoint: str | Path):
        saved = torch.load(checkpoint, map_location='cpu', weights_only=True)
        if saved.get('labels') != list(LABELS) or saved.get('frames') != FRAMES:
            raise ValueError('incompatible short-motion model metadata')
        self.threshold = float(saved['locomotion_threshold'])
        self.model = ShortMotionLSTM()
        self.model.load_state_dict(saved['state_dict'])
        self.model.eval()

    def predict(self, observations):
        missing = {'label': 'unknown', 'confidence': None, 'source': 'a2d_short_locomotion'}
        if not observations:
            return missing | {'reason': 'no observations'}
        cutoff = observations[-1].t - (FRAMES-1)/FPS
        recent = [o for o in observations if o.t >= cutoff-.05]
        if len(recent) < 9:
            return missing | {'reason': 'insufficient observations'}
        times = np.array([o.t for o in recent])
        coords = np.array([[o.cx, o.cy] for o in recent])
        if not np.isfinite(times).all() or not np.isfinite(coords).all() or np.any(np.diff(times) <= 0):
            return missing | {'reason': 'invalid observations'}
        if times[-1]-times[0] < 2.6 or np.diff(times).max() > .65:
            return missing | {'reason': 'short or broken track'}
        target = np.linspace(times[-1]-2.8, times[-1], FRAMES)
        if target[0] < times[0]-.05:
            return missing | {'reason': 'window not covered'}
        covered = int((np.min(np.abs(times[:, None]-target[None, :]), axis=0) <= .12).sum())
        if covered < 9:
            return missing | {'reason': 'less than 60% temporal coverage'}
        sampled = np.column_stack([np.interp(target, times, coords[:, axis]) for axis in range(2)])
        if np.linalg.norm(np.diff(sampled, axis=0), axis=1).max() > .15:
            return missing | {'reason': 'implausible track jump'}
        with torch.inference_mode():
            probability = float(self.model(torch.from_numpy(features(sampled, 2)[None])).softmax(-1)[0, 1])
        return {'label': 'locomotion' if probability >= self.threshold else 'unknown',
                'confidence': probability, 'source': 'a2d_short_locomotion',
                'reason': 'A2D walking/running versus eating; not four-class behavior accuracy',
                'observed_samples': len(recent), 'covered_model_samples': covered}
