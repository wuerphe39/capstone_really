"""Audit available subtype labels and binary detector coverage without inventing labels."""
import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path('artifacts/datasets/fsd50k')
REPORT = Path('docs/evidence/audio_subtype_availability.json')


def main():
    counts = {}
    examples = {}
    for file, part in [('dev', 'train'), ('dev', 'val'), ('eval', 'eval')]:
        rows = list(csv.DictReader((ROOT/'FSD50K.ground_truth'/f'{file}.csv').open(encoding='utf-8')))
        if file == 'dev':
            rows = [r for r in rows if r['split'] == part]
        labels = {r['fname']: set(r['labels'].split(',')) for r in rows}
        key = f'{file}_{part}'
        counts[key] = {name: sum(name in value for value in labels.values())
                       for name in ('Dog', 'Bark', 'Growling', 'Whimper', 'Howl')}
        examples[key] = {name: next((fname for fname, value in labels.items() if name in value), None)
                         for name in ('Bark', 'Growling', 'Whimper', 'Howl')}
    external = json.loads(Path('docs/evidence/audio_external_fsd50k.json').read_text(encoding='utf-8'))
    threshold = external['metrics']['lstm']['threshold']
    by_label = {}
    for label in ('Bark', 'Growling', 'Dog'):
        subset = [r for r in external['records'] if label in r['labels']]
        detected = sum(r['scores']['lstm'] >= threshold for r in subset)
        by_label[label] = {'records': len(subset), 'detected': detected,
                           'recall': detected/len(subset) if subset else None}
    report = {'source': 'FSD50K official ground_truth CSV and previously inspected balanced eval subset',
              'official_counts': counts, 'official_example_ids': examples,
              'existing_binary_dog_detector_by_weak_subtype': by_label,
              'limits': ['Subtype sets overlap and labels are recording-level weak labels',
                         'FSD50K has no explicit Whimper or Howl class in its released vocabulary',
                         'Binary Dog score does not classify Bark/Growling/Whimper/Howl',
                         'No YouTube audio was downloaded; AudioSet publishes IDs/features, not reusable WAVs']}
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'counts': counts, 'binary_eval': by_label}))


if __name__ == '__main__':
    main()
