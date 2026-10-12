"""Conservative track selection; reacquisition starts a new temporal segment.

Spatial/appearance association is a heuristic, never a verified animal identity.
"""
from dataclasses import dataclass

import numpy as np


@dataclass
class Candidate:
    track_id: int
    box: np.ndarray  # normalized xyxy
    confidence: float
    appearance: np.ndarray | None = None


def iou(a, b):
    size = np.maximum(0, np.minimum(a[2:], b[2:])-np.maximum(a[:2], b[:2]))
    intersection = float(np.prod(size))
    return intersection/max(1e-9, float(np.prod(a[2:]-a[:2])+np.prod(b[2:]-b[:2]))-intersection)


class TrackSelector:
    def __init__(self, max_gap=.65, confirmations=3):
        self.max_gap, self.confirmations = max_gap, confirmations
        self.target_id = None
        self.last = None
        self.last_time = None
        self.segment = 0
        self.pending = None
        self.pending_count = 0
        self.pending_time = None
        self.ambiguous = False

    def compatible(self, old, new):
        distance = np.linalg.norm((old.box[:2]+old.box[2:]-new.box[:2]-new.box[2:])/2)
        ratio = np.prod(new.box[2:]-new.box[:2])/max(1e-9, np.prod(old.box[2:]-old.box[:2]))
        appearance_ok = old.appearance is not None and new.appearance is not None and np.minimum(old.appearance, new.appearance).sum() >= .7
        # A moving dog can leave little/no box overlap after one missed sample.
        # Require a bounded center shift, plausible size change and matching
        # appearance instead of IoU, which would reject that valid reconnect.
        return distance <= .15 and .5 <= ratio <= 2 and appearance_ok

    def select(self, candidates, t, dog_count=None):
        count = len(candidates) if dog_count is None else dog_count
        current = next((c for c in candidates if c.track_id == self.target_id), None)
        recent = self.last_time is not None and t-self.last_time <= self.max_gap
        if current is not None and recent and not self.ambiguous:
            crossing = any(c.track_id != current.track_id and iou(c.box, current.box) > .1 for c in candidates)
            jump = np.linalg.norm((current.box[:2]+current.box[2:]-self.last.box[:2]-self.last.box[2:])/2) > .15
            if not crossing and not jump:
                return self._accept(current, t, 'same_id', False)
            self.ambiguous = True
        if current is None and recent and not self.ambiguous and count == 1 and len(candidates) == 1:
            candidate = candidates[0]
            if candidate.confidence >= .35 and self.compatible(self.last, candidate):
                return self._accept(candidate, t, 'short_gap_association', False)
        # Long gaps, crossings or large motion cannot preserve the old sequence.
        # A single stable ID can be sampled again, without asserting same-dog identity.
        if count == 1 and len(candidates) == 1 and candidates[0].confidence >= .35:
            candidate = candidates[0]
            if self.pending is not None and self.pending.track_id == candidate.track_id and t-self.pending_time <= .4 and iou(self.pending.box, candidate.box) >= .2:
                self.pending_count += 1
            else:
                self.pending_count = 1
            self.pending, self.pending_time = candidate, t
            if self.pending_count >= self.confirmations:
                return self._accept(candidate, t, 'new_segment_reacquisition', True)
        else:
            self.pending, self.pending_count = None, 0
        return None, {'event': 'ambiguous_or_missing', 'segment_id': self.segment, 'reset_sequence': True}

    def _accept(self, candidate, t, event, new_segment):
        if new_segment:
            self.segment += 1
        self.target_id, self.last, self.last_time = candidate.track_id, candidate, t
        self.pending, self.pending_count, self.ambiguous = None, 0, False
        return candidate, {'event': event, 'segment_id': self.segment, 'reset_sequence': new_segment,
                           'identity_verified': False}
