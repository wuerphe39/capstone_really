"""Reproducible offline development comparison. No automatic model promotion."""
import argparse
import hashlib
import json
from pathlib import Path

from pet_monitor.temporal_candidates import diagnostics, short_activity, stabilize


def metrics(records, key):
    labels = ['non_locomotion', 'locomotion']
    return {'samples': len(records),
        'decision_ratio': sum(r[key] != 'unknown' for r in records)/len(records) if records else None,
        'correct_fraction': sum(r[key] == r['expected'] for r in records)/len(records) if records else None,
        'recall': {label: sum(r[key] == label and r['expected'] == label for r in records)/n if
                  (n := sum(r['expected'] == label for r in records)) else None for label in labels},
        'support': {label: sum(r['expected'] == label for r in records) for label in labels}}


def run(reference, video_reports, output):
    data = json.loads(reference.read_text(encoding='utf-8'))
    rows = []
    for record in data['records']:
        # Only fully homogeneous publisher labels support the last 3 s reference.
        if record['reference_purity'] != 1:
            continue
        now = record['native_pts_end']-record['native_pts_start']
        guarded = short_activity(record['points'], now, fixed_camera=False)
        exploratory = short_activity(record['points'], now, fixed_camera=True)
        rows.append({'video_id': record['video_id'], 'shot': record['shot'], 'expected': record['expected'],
                     'baseline': record['v2'], 'guarded_short': guarded['label'],
                     'unverified_camera_ablation': exploratory['label'], 'short_reason': exploratory['reason']})
    videos = []
    for path in video_reports:
        report = json.loads(path.read_text(encoding='utf-8'))
        smoothed = stabilize(report['predictions'])
        flips = lambda seq: sum(a['label'] != b['label'] for a, b in zip(seq, seq[1:])
                               if 'unknown' not in (a['label'], b['label']))
        videos.append({'report': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                       'baseline': diagnostics(report),
                       'stabilized': diagnostics({**report, 'predictions': smoothed}),
                       'baseline_label_switches': flips(report['predictions']),
                       'stabilized_label_switches': flips(smoothed),
                       'changed_predictions': sum(a['label'] != b['label'] for a,b in zip(report['predictions'],smoothed)),
                       'behavior_accuracy': None})
    result = {'reference': reference.name, 'reference_sha256': hashlib.sha256(reference.read_bytes()).hexdigest(),
              'scope': 'previously examined TigDog development subset, coarse homogeneous locomotion labels',
              'metrics': {key: metrics(rows, key) for key in ['baseline', 'guarded_short', 'unverified_camera_ablation']},
              'records': rows, 'video_diagnostics': videos, 'promoted': False,
              'four_class_accuracy': None,
              'decision': 'Keep baseline: no fixed-camera verification or four-class references. Reduced switches alone do not prove accuracy.',
              'limitations': ['one-class subset cannot establish overall accuracy or specificity',
                              'unverified-camera ablation is not an eligible deployment candidate',
                              'smoothing delay and behavior transitions need independent temporal annotations']}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'metrics': result['metrics'], 'promoted': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--reference', type=Path, default=Path('docs/evidence/tigdog_original_evaluation.json'))
    parser.add_argument('--video-report', type=Path, action='append', default=[])
    parser.add_argument('--output', type=Path, default=Path('docs/evidence/temporal_candidates_evaluation.json'))
    args = parser.parse_args()
    run(args.reference, args.video_report, args.output)
