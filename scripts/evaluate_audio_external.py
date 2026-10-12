"""Frozen ESC-trained models on source-disjoint FSD50K selected evaluation clips."""
import hashlib
import json
from pathlib import Path

import torch

from pet_monitor.audio import analyze_wav
from pet_monitor.audio_lstm import AudioPredictor, binary_metrics


def main():
    torch.set_num_threads(2)
    root = Path('artifacts/datasets/fsd50k/eval_subset')
    manifest_path = root/'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    predictors = {name:AudioPredictor(f'artifacts/audio_lstm/esc50_{name}.pt') for name in ('pooled','lstm')}
    rows = []
    for item in manifest['records']:
        path = root/item['filename']
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('source checksum mismatch')
        scores = {name:predictor.predict(path)['dog_score'] for name,predictor in predictors.items()}
        scores['energy'] = float(analyze_wav(path)['context']['bark']['count'] > 0)
        rows.append({**item, 'scores':scores})
    expected = [row['expected'] for row in rows]
    results = {name:binary_metrics(expected,[r['scores'][name] for r in rows],
                                  predictors[name].threshold if name in predictors else .5)
               for name in ('energy','pooled','lstm')}
    report = {'source':manifest['source'],'manifest_sha256':hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        'metrics':results, 'records':rows, 'promoted':False,
        'checkpoints':{name:hashlib.sha256(Path(f'artifacts/audio_lstm/esc50_{name}.pt').read_bytes()).hexdigest() for name in predictors},
        'limitations':['balanced CC0/CC BY selected subset; not population prevalence',
                       'clip-level Dog labels, not barking timestamps or emotion',
                       '5-second window scores max-pooled for up to 30-second clips; thresholds frozen from ESC validation',
                       'ESC source IDs excluded; transformed duplicate audio cannot be fully ruled out',
                       'no source-dog identity annotations; not individual-dog held-out validation']}
    Path('docs/evidence/audio_external_fsd50k.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(results),flush=True)


if __name__ == '__main__':
    main()
