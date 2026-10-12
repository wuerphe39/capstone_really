"""Bounded, merged audio-triggered video intervals; no visual inference."""
from dataclasses import dataclass, field
import math


@dataclass
class EventWindow:
    start: float
    end: float
    clip_ids: list[str] = field(default_factory=list)


class EventPlanner:
    """Feed chronologically analysed audio, then drain only beyond the merge horizon.

    Waiting through pre-roll after the event end ensures a later detection whose
    pre-roll overlaps is merged before publishing. max_event_s bounds long runs.
    """
    def __init__(self, pre_s=5., post_s=5., max_event_s=60.):
        if not all(math.isfinite(v) for v in (pre_s, post_s, max_event_s)) or not (
            0 <= pre_s <= 15 and 0 <= post_s <= 15 and
            pre_s + post_s + 5 <= max_event_s <= 120
        ):
            raise ValueError('invalid event bounds')
        self.pre, self.post, self.maximum = pre_s, post_s, max_event_s
        self.pending: list[EventWindow] = []

    def add(self, start, end, clip_id):
        if not math.isfinite(start) or not math.isfinite(end) or end <= start:
            raise ValueError('invalid detection window')
        a, b = start-self.pre, end+self.post
        if self.pending and a <= self.pending[-1].end:
            event = self.pending[-1]
            # Split a long continuous event rather than pin the entire recording.
            if max(event.end, b)-event.start <= self.maximum:
                event.end = max(event.end, b)
                if clip_id not in event.clip_ids:
                    event.clip_ids.append(clip_id)
                return
        self.pending.append(EventWindow(a, b, [clip_id]))

    def drain(self, analysed_until, final=False):
        ready, waiting = [], []
        for event in self.pending:
            (ready if final or analysed_until >= event.end+self.pre else waiting).append(event)
        self.pending = waiting
        return ready


def candidate_windows(analysis):
    """Only audio model positives trigger recording, never energy alone or failed models."""
    model = analysis.get('audio_model') or analysis.get('audio_lstm') or {}
    threshold = model.get('threshold')
    if threshold is None or not math.isfinite(threshold) or not 0 <= threshold <= 1:
        return []
    return [w for w in model.get('windows', [])
            if all(math.isfinite(w.get(k, float('nan'))) for k in ('start_s', 'end_s', 'dog_score'))
            and 0 <= w['start_s'] < w['end_s'] <= 30
            and threshold <= w['dog_score'] <= 1]
