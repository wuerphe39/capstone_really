"""Frozen ESC split experiment. Select epoch/threshold using validation only."""
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import torch

from pet_monitor.audio import analyze_wav
from pet_monitor.audio_lstm import AudioClassifier, binary_metrics, logmel

ROOT = Path('artifacts/datasets/esc50')
OUTPUT = Path('artifacts/audio_lstm')


def main():
    torch.set_num_threads(2)
    torch.manual_seed(20261011)
    np.random.seed(20261011)
    manifest_path = ROOT/'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    rows = manifest['records']
    OUTPUT.mkdir(parents=True, exist_ok=True)
    inputs = []
    for i, row in enumerate(rows):
        path = ROOT/'audio'/row['filename']
        if hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('audio checksum mismatch')
        inputs.append(logmel(path))
        if i % 250 == 0: print(f'features {i}/{len(rows)}', flush=True)
    x = torch.stack(inputs)
    y = torch.tensor([int(r['category'] == 'dog') for r in rows])
    masks = {split: torch.tensor([r['split'] == split for r in rows]) for split in ('train','validation','test')}
    mean = x[masks['train']].mean((0,1)); std = x[masks['train']].std((0,1)).clamp_min(.01)
    x = (x-mean)/std
    results = {}
    for kind in ('pooled', 'lstm'):
        torch.manual_seed(20261011)
        model = AudioClassifier(kind)
        optimizer = torch.optim.Adam(model.parameters(), lr=.001)
        train_y = y[masks['train']]
        weights = torch.tensor([1., float((train_y == 0).sum()/(train_y == 1).sum())])
        loss_fn = torch.nn.CrossEntropyLoss(weight=weights)
        best = None
        dataset = torch.utils.data.TensorDataset(x[masks['train']], train_y)
        loader = torch.utils.data.DataLoader(dataset, batch_size=32, shuffle=True)
        for epoch in range(1, 21):
            model.train()
            for batch, labels in loader:
                optimizer.zero_grad(); loss = loss_fn(model(batch),labels)
                loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(), 5); optimizer.step()
            model.eval()
            with torch.inference_mode():
                p = model(x[masks['validation']]).softmax(-1)[:,1].numpy()
            candidates = [binary_metrics(y[masks['validation']].numpy(), p, t) for t in np.linspace(.05,.95,19)]
            score = max(candidates, key=lambda m:(m['f1'],m['precision'],m['threshold']))
            if best is None or score['f1'] > best['validation']['f1']:
                best = {'epoch':epoch, 'validation':score, 'state':copy.deepcopy(model.state_dict())}
            print(f'{kind} epoch {epoch}: validation F1 {score["f1"]:.3f}', flush=True)
        model.load_state_dict(best.pop('state'))
        with torch.inference_mode():
            probabilities = model(x[masks['test']]).softmax(-1)[:,1].numpy()
        threshold = best['validation']['threshold']
        checkpoint = OUTPUT/f'esc50_{kind}.pt'
        torch.save({'state_dict':model.state_dict(), 'mean':mean, 'std':std, 'threshold':threshold,
                    'kind':kind, 'labels':['other','dog'], 'sample_rate':16000, 'window_s':5,
                    'training_source':manifest['revision']}, checkpoint)
        results[kind] = {**best, 'test':binary_metrics(y[masks['test']].numpy(), probabilities, threshold),
                        'checkpoint_sha256':hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
                        'predictions':[{'filename':r['filename'], 'expected':int(r['category']=='dog'), 'dog_score':float(p)}
                                       for r,p in zip([r for r in rows if r['split']=='test'],probabilities)]}
    test_rows = [r for r in rows if r['split']=='test']
    energy = [float(analyze_wav(ROOT/'audio'/r['filename'])['context']['bark']['count']>0) for r in test_rows]
    results['energy'] = {'test':binary_metrics([r['category']=='dog' for r in test_rows],energy)}
    report = {'dataset_revision':manifest['revision'], 'manifest_sha256':hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
              'split':manifest['policy'], 'seed':20261011, 'models':results, 'promoted':False,
              'limitations':['Dog clip-level label is not precise bark onset/offset or emotion',
                             'only 8 positive clips in frozen test fold; not household validation',
                             'previous 20-file pilot used fold 1, now training-only',
                             'no pretrained encoder evaluated in this report']}
    destination = Path('docs/evidence/audio_baselines_esc50.json')
    destination.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v['test'] for k,v in results.items()}),flush=True)


if __name__ == '__main__':
    main()
