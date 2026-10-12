"""Recheck already-downloaded FSD50K evaluation clips with the frozen audio LSTM.

This is a presentation case study, not a new independent accuracy estimate.
"""
import hashlib
import json
from pathlib import Path

import torch

from pet_monitor.audio_lstm import AudioPredictor


ROOT = Path('artifacts/datasets/fsd50k/eval_subset')
HOME_LABELS = {'Door', 'Speech', 'Chatter', 'Domestic_sounds_and_home_sounds',
               'Bell', 'Wind_chime', 'Dishes', 'Vacuum_cleaner'}


def main():
    torch.set_num_threads(2)
    manifest = json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))
    selected = [r for r in manifest['records'] if
                ('Bark' in r['labels'] and 'Dog' in r['labels'] and HOME_LABELS.intersection(r['labels']))
                or (not r['expected'] and HOME_LABELS.intersection(r['labels']))]
    predictor = AudioPredictor('artifacts/audio_lstm/esc50_lstm.pt')
    rows = []
    for row in selected:
        source_id = row['source_id']
        path = ROOT/row['filename']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256']
        assert HOME_LABELS.intersection(row['labels'])
        prediction = predictor.predict(path)
        rows.append({'source_id':source_id,'title':row['title'],'labels':row['labels'],
                     'home_labels':sorted(HOME_LABELS.intersection(row['labels'])),
                     'reference_bark': bool(row['expected']),
                     'duration_s':row['duration_s'],'uploader':row['uploader'],
                     'license':row['license'],'sha256':row['sha256'],
                     'threshold':prediction['threshold'],'score':prediction['dog_score'],
                     'detected':prediction['dog_score'] >= prediction['threshold'],
                     'windows':prediction['windows']})
    positives=[r for r in rows if r['reference_bark']]
    negatives=[r for r in rows if not r['reference_bark']]
    out = {'source':manifest['source'],'official_split':'eval',
           'use':'previously inspected evaluation clips; presentation case study only',
           'model':'frozen artifacts/audio_lstm/esc50_lstm.pt',
           'limits':['FSD50K labels are clip-level; exact bark timing and sound overlap not annotated',
                     'Dog/Bark labels do not identify this household pet or prove a source is in the room',
                     'No threshold or checkpoint tuning from these results'],
           'cases':rows,'positive_detected':sum(r['detected'] for r in positives),
           'positive_total':len(positives),'negative_false_positives':sum(r['detected'] for r in negatives),
           'negative_total':len(negatives)}
    target = Path('artifacts/household_bark_20261012/model_results.json')
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'positive_detected':out['positive_detected'],'positive_total':out['positive_total'],
                      'negative_false_positives':out['negative_false_positives'],'negative_total':out['negative_total'],
                      'cases':[{'id':r['source_id'],'score':round(r['score'],4),
                                'threshold':r['threshold'],'detected':r['detected'],
                                'reference_bark':r['reference_bark'],
                                'home_labels':r['home_labels']} for r in rows]},ensure_ascii=False))


if __name__=='__main__':
    main()
