r"""Evaluate the operating detector (YAMNet Bark, threshold 0.05) on household sounds and short barks from FSD50K eval.

Needs the clips from `python -m scripts.prepare_fsd50k_household` and the running YAMNet service (port 8030). The threshold is
the fixed operating value and is not tuned here. A clip counts as "bark" when its best 5 s window reaches the threshold.
Negatives are speech, doorbell, knock, telephone/ringtone, music, laughter, crying, cat, alarm, bell, door and other animals;
positives are CC0/CC-BY clips labelled Bark, also split by clip length (a proxy for short barks).

    .\.venv\Scripts\python.exe -m scripts.evaluate_yamnet_fsd50k_household

Per-window scores: artifacts/fsd_household_eval/scores.json (git-ignored). Summary: docs/evidence/yamnet_fsd50k_household.json.
"""
import argparse
import json
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from scripts.evaluate_yamnet_esc50 import wilson

DATA = Path('artifacts/datasets/fsd50k/household_eval')
THRESHOLD = 0.05


def windows(url, path):
    for attempt in range(3):
        try:
            r = requests.post(url, data=path.read_bytes(), headers={'Content-Type': 'audio/wav'}, timeout=120)
            r.raise_for_status()
            return [w['bark_score'] for w in r.json()['windows']]
        except requests.RequestException:
            time.sleep(1 + attempt)
    raise RuntimeError(f'service failed on {path.name}')


def bucket(seconds):
    return '<1 s' if seconds < 1 else '1-3 s' if seconds < 3 else '>=3 s'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--url', default='http://127.0.0.1:8030/analyze')
    ap.add_argument('--threads', type=int, default=3)
    ap.add_argument('--out', type=Path, default=Path('docs/evidence/yamnet_fsd50k_household.json'))
    args = ap.parse_args()

    records = json.loads((DATA / 'manifest.json').read_text(encoding='utf-8'))['records']
    cache = Path('artifacts/fsd_household_eval/scores.json')
    scores = json.loads(cache.read_text(encoding='utf-8')) if cache.exists() else {}
    todo = [r for r in records if r['filename'] not in scores]
    with ThreadPoolExecutor(args.threads) as pool:
        for i, (r, w) in enumerate(zip(todo, pool.map(lambda r: windows(args.url, DATA / r['filename']), todo)), 1):
            scores[r['filename']] = w
            if i % 100 == 0:
                print(f'{i}/{len(todo)} scored', flush=True)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(scores), encoding='utf-8')

    best = lambda r: max(scores[r['filename']])
    pos = [r for r in records if r['expected']]
    neg = [r for r in records if not r['expected']]
    tp = sum(best(r) >= THRESHOLD for r in pos)
    fp = sum(best(r) >= THRESHOLD for r in neg)
    nwin = sum(len(scores[r['filename']]) for r in neg)
    fpwin = sum(s >= THRESHOLD for r in neg for s in scores[r['filename']])

    by_len = defaultdict(lambda: [0, 0])
    for r in pos:
        b = bucket(r['duration_s']); by_len[b][1] += 1; by_len[b][0] += best(r) >= THRESHOLD
    groups = defaultdict(lambda: {'clips': 0, 'false_alarm_clips': 0, 'windows': 0, 'false_alarm_windows': 0})
    for r in neg:
        g = groups[r['group']]; g['clips'] += 1; g['false_alarm_clips'] += best(r) >= THRESHOLD
        g['windows'] += len(scores[r['filename']]); g['false_alarm_windows'] += sum(s >= THRESHOLD for s in scores[r['filename']])
    missed = sorted(((r['filename'], r['duration_s'], round(best(r), 4)) for r in pos if best(r) < THRESHOLD), key=lambda x: x[2])
    sweep = [{'threshold': th, 'bark_detected': sum(best(r) >= th for r in pos), 'bark_total': len(pos),
              'false_alarm_clips': sum(best(r) >= th for r in neg), 'negative_clips': len(neg)} for th in (0.02, 0.05, 0.1, 0.2, 0.5)]

    summary = {
        'dataset': 'FSD50K eval subset (official exhaustive annotation), CC0/CC-BY; see manifest', 'detector': 'YAMNet Bark direct score, max over 5 s windows',
        'threshold': THRESHOLD, 'threshold_note': 'fixed operating value; not chosen from this evaluation',
        'bark_clips': len(pos), 'negative_clips': len(neg),
        'bark_detected': tp, 'bark_recall': round(tp / len(pos), 3), 'bark_recall_95ci': [round(x, 3) for x in wilson(tp, len(pos))],
        'bark_recall_by_clip_length': {b: {'detected': k, 'clips': n, 'recall': round(k / n, 3), 'ci95': [round(x, 3) for x in wilson(k, n)]}
                                       for b, (k, n) in sorted(by_len.items())},
        'false_alarm_clips': fp, 'false_alarm_clip_rate': round(fp / len(neg), 4), 'false_alarm_clip_95ci': [round(x, 4) for x in wilson(fp, len(neg))],
        'false_alarm_windows': fpwin, 'negative_windows': nwin, 'false_alarm_window_rate': round(fpwin / nwin, 4),
        'false_alarm_window_95ci': [round(x, 4) for x in wilson(fpwin, nwin)],
        'by_negative_group': {g: {**v, 'false_alarm_clip_rate': round(v['false_alarm_clips'] / v['clips'], 3),
                                  'ci95': [round(x, 3) for x in wilson(v['false_alarm_clips'], v['clips'])]} for g, v in sorted(groups.items())},
        'missed_bark_clips': missed[:25], 'threshold_sweep_informational': sweep,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')
    print('bark recall %d/%d  by length %s' % (tp, len(pos), {b: f'{k}/{n}' for b, (k, n) in sorted(by_len.items())}))
    print('negative clips FA %d/%d (%.1f%%) | windows FA %d/%d (%.1f%%)' % (fp, len(neg), 100 * fp / len(neg), fpwin, nwin, 100 * fpwin / nwin))
    for g, v in sorted(groups.items(), key=lambda kv: -kv[1]['false_alarm_clips'] / kv[1]['clips']):
        print('  %-13s %3d/%-3d clips' % (g, v['false_alarm_clips'], v['clips']))


if __name__ == '__main__':
    main()
