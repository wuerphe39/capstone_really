"""Offline candidates only. Never replace unknown four-class LSTM output.

Short activity measures image-plane movement, not pacing, emotion or disease.
Thresholds are frozen engineering hypotheses, not calibrated dog behavior labels.
"""
from collections import Counter, deque

import numpy as np


def short_activity(points, now, fixed_camera=False, window_s=3.0):
    if not fixed_camera:
        return {'label': 'unknown', 'reason': 'fixed camera not verified'}
    recent = [p for p in points if now-window_s <= p['t'] <= now]
    if len(recent) < 12:
        return {'label': 'unknown', 'reason': 'short window tracking coverage'}
    times = np.array([p['t'] for p in recent])
    coords = np.array([[p['cx'], p['cy']] for p in recent])
    if not np.isfinite(times).all() or not np.isfinite(coords).all():
        return {'label': 'unknown', 'reason': 'invalid tracking'}
    if (times[-1]-times[0] < 2.6 or now-times[-1] > .25 or
            np.any(np.diff(times) <= 0) or np.max(np.diff(times)) > .4):
        return {'label': 'unknown', 'reason': 'short window tracking gap'}
    if len({p.get('segment_id', 0) for p in recent}) != 1:
        return {'label': 'unknown', 'reason': 'identity segment changed'}
    if np.max(np.linalg.norm(np.diff(coords, axis=0), axis=1)) > .15:
        return {'label': 'unknown', 'reason': 'implausible track jump'}
    # Median bins suppress single-frame detector jitter without time stretching.
    centers = np.array([np.median(a, axis=0) for a in np.array_split(coords, 6)])
    extent = float(np.linalg.norm(np.ptp(centers, axis=0)))
    label = 'non_locomotion' if extent <= .025 else 'locomotion' if extent >= .06 else 'unknown'
    return {'label': label, 'reason': 'image-plane extent; coarse candidate only', 'extent': extent}


def stabilize(predictions, max_gap_s=.4):
    """Causal majority of last 3 valid outputs. Unknown and gaps reset history."""
    recent, result, previous = deque(maxlen=3), [], None
    for prediction in predictions:
        item = dict(prediction)
        if previous is not None and (item['t'] <= previous or item['t']-previous > max_gap_s):
            recent.clear()
        previous = item['t']
        if item['label'] == 'unknown':
            recent.clear()
        else:
            recent.append(item['label'])
            if len(recent) == 3:
                label, votes = Counter(recent).most_common(1)[0]
                if votes >= 2:
                    item['label'] = label
        result.append(item)
    return result


def diagnostics(report):
    reasons, seconds = Counter(), Counter()
    predictions = report.get('predictions', [])
    duration = float(report['duration_s'])
    for i, item in enumerate(predictions):
        end = predictions[i+1]['t'] if i+1 < len(predictions) else duration
        width = max(0, min(end, duration)-max(0, item['t']))
        seconds[item['label']] += width
        if item['label'] == 'unknown':
            reasons[item.get('reason', 'unreported')] += width
    events = Counter(item.get('event', 'unreported') for item in report.get('tracking_diagnostics', []))
    total = sum(seconds.values())
    return {'duration_s': duration, 'covered_timeline_s': total,
            'decision_ratio': (total-seconds['unknown'])/total if total else 0,
            'seconds_by_label': dict(seconds), 'unknown_reason_seconds': dict(reasons),
            'tracking_events': dict(events), 'accuracy': None,
            'note': 'coverage is not correctness; unknown includes warm-up and tracking failures'}
