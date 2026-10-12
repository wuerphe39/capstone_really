import json
from pathlib import Path

from pet_monitor.audio import analyze_wav


def main():
    folder = Path('artifacts/media')
    records = []
    for item in json.loads((folder / 'manifest.json').read_text(encoding='utf-8')):
        if item['type'] != 'audio':
            continue
        result = analyze_wav(folder / item['filename'])
        records.append({'filename': item['filename'], 'category': item['category'],
                        'expected_dog_clip': item['category'] == 'dog',
                        'candidate_present': result['context']['bark']['count'] > 0,
                        'candidate_count': result['context']['bark']['count'],
                        'sha256': item['sha256'], 'analysis': result})
    tp = sum(r['expected_dog_clip'] and r['candidate_present'] for r in records)
    fp = sum(not r['expected_dog_clip'] and r['candidate_present'] for r in records)
    fn = sum(r['expected_dog_clip'] and not r['candidate_present'] for r in records)
    tn = sum(not r['expected_dog_clip'] and not r['candidate_present'] for r in records)
    report = {'scope': 'fixed 20-clip pilot, candidate presence only; no per-bark ground truth',
              'true_positive_clips': tp, 'false_positive_clips': fp, 'false_negative_clips': fn,
              'true_negative_clips': tn, 'records': records,
              'limitation': 'energy cannot identify source; this is not validated bark classification accuracy'}
    Path('artifacts/audio_evaluation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'records'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
