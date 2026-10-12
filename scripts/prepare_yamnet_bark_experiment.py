"""Make a source-disjoint, explicitly Bark-labeled experiment manifest."""
import hashlib
import json
from pathlib import Path

from scripts.compare_audio_lstm import groups


ROOT = Path('artifacts/yamnet_bark_experiment')
SEED = 'yamnet-bark-v1'
NEGATIVE_ESC_LIMIT = 80


def selected_rows(grouped):
    result = {}
    for partition in ('train', 'val', 'eval'):
        fsd_key = {'train': 'fsd_train', 'val': 'fsd_val', 'eval': 'fsd_eval'}[partition]
        esc_key = {'train': 'esc_train', 'val': 'esc_val', 'eval': 'esc_test'}[partition]
        explicit_bark = [r for r in grouped[fsd_key] if 'Bark' in r['labels']]
        non_dog = [r for r in grouped[fsd_key] if not r['expected']]
        esc_other = [r for r in grouped[esc_key] if not r['expected']]
        esc_other.sort(key=lambda r: hashlib.sha256(
            (SEED + ':' + r['source_id']).encode()).hexdigest())
        selected = [(r, 1) for r in explicit_bark] + [(r, 0) for r in non_dog]
        selected += [(r, 0) for r in esc_other[:NEGATIVE_ESC_LIMIT]]
        if not explicit_bark or not non_dog:
            raise ValueError(f'{partition}: missing explicit Bark positives or non-Dog negatives')
        result[partition] = [{
            'id': f'{fsd_key if r in grouped[fsd_key] else esc_key}:{r["source_id"]}',
            'source_id': r['source_id'], 'path': str(r['path'].resolve()),
            'sha256': r['sha256'], 'label': label,
            'source': 'fsd50k' if r in grouped[fsd_key] else 'esc50',
            'original_split': r['split'], 'labels': r.get('labels', [r.get('category')]),
        } for r, label in selected]
    hashes = [r['sha256'] for rows in result.values() for r in rows]
    if len(hashes) != len(set(hashes)):
        raise ValueError('duplicate file hash across selected rows')
    return result


def main():
    rows = selected_rows(groups())
    ROOT.mkdir(parents=True, exist_ok=True)
    payload = {'task': 'explicit Bark vs non-Dog clip classification',
               'selection': 'all FSD50K Bark, all FSD50K non-Dog, 80 deterministic ESC non-Dog per split',
               'excluded': 'FSD Dog without Bark and ESC Dog are not assigned a Bark label',
               'evaluation_scope': 'previously inspected official eval/test; development audit, not blind test',
               'rows': rows}
    (ROOT/'manifest.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                      encoding='utf-8')
    print({part: {'total': len(items), 'bark': sum(r['label'] for r in items)}
           for part, items in rows.items()})


if __name__ == '__main__':
    main()
