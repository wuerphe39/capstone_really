r"""Evaluate the operating detector (YAMNet Bark direct score, threshold 0.05) on all 2,000 ESC-50 clips.

ESC-50 comes from Freesound, not from AudioSet (YAMNet's pre-training set), and YAMNet is not trained here, so no
training/selection overlap with this script: the threshold is the fixed operating value, not tuned on these clips.
Each 5 s clip is sent to the running YAMNet service; a clip is predicted "bark" when its best window score >= threshold.
Positive = category `dog` (40 clips); everything else (1,960) is negative, including cat, crow, rooster and household sounds.

    py -3.12 -m petmind.yamnet_service.app --port 8030        # service must be running
    .\.venv\Scripts\python.exe -m scripts.prepare_esc50        # one-time download (about 0.9 GB, git-ignored)
    .\.venv\Scripts\python.exe -m scripts.evaluate_yamnet_esc50

Per-clip scores go to artifacts/esc50_eval/scores.json (git-ignored); the summary goes to docs/evidence/yamnet_esc50_full.json.
"""
import argparse
import csv
import json
import math
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

ROOT = Path('artifacts/datasets/esc50')
THRESHOLD = 0.05          # fixed operating threshold (PETMIND yamnet detector); never chosen from this evaluation
HOUSEHOLD = ['door_wood_knock', 'mouse_click', 'keyboard_typing', 'door_wood_creaks', 'can_opening', 'washing_machine',
             'vacuum_cleaner', 'clock_alarm', 'clock_tick', 'glass_breaking', 'toilet_flush', 'brushing_teeth',
             'footsteps', 'laughing', 'crying_baby', 'sneezing', 'coughing', 'breathing', 'snoring', 'drinking_sipping',
             'siren', 'car_horn', 'helicopter', 'train', 'airplane', 'hand_saw', 'chainsaw', 'church_bells', 'clapping']
ANIMALS = ['rooster', 'pig', 'cow', 'frog', 'cat', 'hen', 'insects', 'sheep', 'crow']


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def score_clip(url, path):
    for attempt in range(3):
        try:
            r = requests.post(url, data=path.read_bytes(), headers={'Content-Type': 'audio/wav'}, timeout=60)
            r.raise_for_status()
            windows = r.json()['windows']
            return max(w['bark_score'] for w in windows)
        except requests.RequestException:
            time.sleep(1 + attempt)
    raise RuntimeError(f'service failed on {path.name}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--url', default='http://127.0.0.1:8030/analyze')
    ap.add_argument('--threads', type=int, default=3)
    ap.add_argument('--limit', type=int, help='only the first N clips (smoke test)')
    ap.add_argument('--out', type=Path, default=Path('docs/evidence/yamnet_esc50_full.json'))
    args = ap.parse_args()

    rows = list(csv.DictReader((ROOT / 'esc50.csv').open(encoding='utf-8')))
    if args.limit:
        rows = rows[:args.limit]
    cache = Path('artifacts/esc50_eval/scores.json')
    scores = json.loads(cache.read_text(encoding='utf-8')) if cache.exists() else {}
    todo = [r for r in rows if r['filename'] not in scores]
    t0 = time.time()
    with ThreadPoolExecutor(args.threads) as pool:
        for i, (row, s) in enumerate(zip(todo, pool.map(lambda r: score_clip(args.url, ROOT / 'audio' / r['filename']), todo)), 1):
            scores[row['filename']] = s
            if i % 200 == 0:
                print(f'{i}/{len(todo)} scored ({time.time() - t0:.0f}s)', flush=True)
                cache.parent.mkdir(parents=True, exist_ok=True); cache.write_text(json.dumps(scores), encoding='utf-8')
    cache.parent.mkdir(parents=True, exist_ok=True); cache.write_text(json.dumps(scores), encoding='utf-8')

    pos = [r for r in rows if r['category'] == 'dog']
    neg = [r for r in rows if r['category'] != 'dog']
    tp = sum(scores[r['filename']] >= THRESHOLD for r in pos); fn = len(pos) - tp
    fp = sum(scores[r['filename']] >= THRESHOLD for r in neg); tn = len(neg) - fp
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / len(pos) if pos else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0

    by_cat = defaultdict(lambda: [0, 0])
    for r in neg:
        by_cat[r['category']][1] += 1
        by_cat[r['category']][0] += scores[r['filename']] >= THRESHOLD
    fp_cats = sorted(((c, k, n) for c, (k, n) in by_cat.items() if k), key=lambda x: -x[1])
    house = [(c, *by_cat[c]) for c in HOUSEHOLD if c in by_cat]
    animals = [(c, *by_cat[c]) for c in ANIMALS if c in by_cat]
    hk = sum(k for _, k, _ in house); hn = sum(n for _, _, n in house)
    dog_scores = sorted(scores[r['filename']] for r in pos)
    quant = lambda q: dog_scores[min(len(dog_scores) - 1, int(q * len(dog_scores)))]
    missed = sorted(((r['filename'], round(scores[r['filename']], 4)) for r in pos if scores[r['filename']] < THRESHOLD), key=lambda x: x[1])
    sweep = []
    for th in (0.02, 0.05, 0.1, 0.2, 0.5):
        a = sum(scores[r['filename']] >= th for r in pos); b = sum(scores[r['filename']] >= th for r in neg)
        sweep.append({'threshold': th, 'dog_detected': a, 'dog_total': len(pos), 'false_alarms': b, 'negatives': len(neg)})

    summary = {
        'dataset': 'ESC-50 (all 2,000 clips, official revision 33c8ce9e)', 'detector': 'YAMNet Bark direct score, max over windows',
        'threshold': THRESHOLD, 'threshold_note': 'fixed operating value; not chosen from this evaluation',
        'dog_clips': len(pos), 'other_clips': len(neg),
        'confusion': {'tp': tp, 'fn': fn, 'fp': fp, 'tn': tn},
        'recall': round(rec, 3), 'recall_95ci': [round(x, 3) for x in wilson(tp, len(pos))],
        'false_alarm_rate': round(fp / len(neg), 4), 'false_alarm_95ci': [round(x, 4) for x in wilson(fp, len(neg))],
        'precision': round(prec, 3), 'f1': round(f1, 3),
        'precision_note': 'depends on the 40:1,960 class ratio of this set, not on a home',
        'dog_score_quantiles': {q: round(quant(q), 3) for q in (0.1, 0.25, 0.5, 0.75, 0.9)},
        'missed_dog_clips': missed,
        'false_alarm_categories': [{'category': c, 'false_alarms': k, 'clips': n} for c, k, n in fp_cats],
        'household_sounds': {'false_alarms': hk, 'clips': hn, 'categories': [{'category': c, 'false_alarms': k, 'clips': n} for c, k, n in house]},
        'animal_sounds': [{'category': c, 'false_alarms': k, 'clips': n} for c, k, n in animals],
        'threshold_sweep_informational': sweep,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({k: summary[k] for k in ('confusion', 'recall', 'recall_95ci', 'false_alarm_rate', 'false_alarm_95ci', 'precision', 'f1')}, ensure_ascii=False))
    print('missed dog clips:', len(missed), '| false-alarm categories:', [(c, k, n) for c, k, n in fp_cats][:12])
    print('household false alarms: %d / %d' % (hk, hn))
    print('sweep (informational):', sweep)


if __name__ == '__main__':
    main()
