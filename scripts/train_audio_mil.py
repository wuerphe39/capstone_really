"""Additional FSD training with clip-level multiple-instance supervision.

No claim that every five-second window in a Dog-labelled recording contains Dog.
Frozen ESC validation selects epoch/threshold; evaluation files never train.
"""
import copy
import hashlib
import io
import json
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from torch.nn import functional as F

from pet_monitor.audio_lstm import AudioClassifier, binary_metrics, logmel

ESC = Path('artifacts/datasets/esc50')
FSD = Path('artifacts/datasets/fsd50k')
OUTPUT = Path('artifacts/audio_lstm')


def features(path):
    audio, rate = sf.read(path, dtype='float32', always_2d=True)
    if not len(audio) or len(audio) / rate > 30 or not np.isfinite(audio).all():
        raise ValueError('expected finite nonempty audio up to 30 seconds')
    result = []
    for start in range(0, len(audio), rate * 5):
        buffer = io.BytesIO()
        sf.write(buffer, audio[start:start + rate * 5], rate, format='WAV', subtype='FLOAT')
        buffer.seek(0)
        result.append(logmel(buffer))
    return torch.stack(result)


def bag_logits(logits, lengths):
    """Max dog log-odds per recording, matching inference max probability."""
    if any(n <= 0 for n in lengths) or sum(lengths) != len(logits):
        raise ValueError('invalid bag lengths')
    margins = logits[:, 1] - logits[:, 0]
    return torch.stack([part.max() for part in margins.split(lengths)])


def assert_disjoint(left, right):
    for key in ('source_id', 'sha256'):
        if {str(r[key]) for r in left} & {str(r[key]) for r in right}:
            raise ValueError(f'training/evaluation overlap: {key}')


def load_rows():
    esc_manifest = json.loads((ESC / 'manifest.json').read_text(encoding='utf-8'))
    esc = [{**r, 'source_id': str(r['src_file']), 'expected': int(r['category'] == 'dog'),
            'path': ESC / 'audio' / r['filename']} for r in esc_manifest['records']]
    groups = {s: [r for r in esc if r['split'] == s] for s in ('train', 'validation', 'test')}
    fsd = {}
    for split in ('dev', 'eval'):
        root = FSD / f'{split}_subset'
        rows = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))['records']
        fsd[split] = [{**r, 'path': root / r['filename']} for r in rows]
    if any(r['original_split'] != 'train' for r in fsd['dev']):
        raise ValueError('FSD additional training must use official train only')
    assert_disjoint(fsd['dev'], esc + fsd['eval'])
    assert_disjoint(groups['train'], groups['validation'] + groups['test'] + fsd['eval'])
    groups['train'] += fsd['dev']
    groups['fsd_test'] = fsd['eval']
    return groups


def main():
    torch.set_num_threads(2)
    torch.manual_seed(20261011)
    groups = load_rows()
    inputs = {}
    for split, rows in groups.items():
        inputs[split] = []
        for row in rows:
            if hashlib.sha256(row['path'].read_bytes()).hexdigest() != row['sha256']:
                raise ValueError('audio checksum mismatch')
            inputs[split].append(features(row['path']))
        print(f'{split}: {len(rows)} full recordings prepared', flush=True)
    reports = {}
    for kind in ('pooled', 'lstm'):
        torch.manual_seed(20261011)
        original = OUTPUT / f'esc50_{kind}.pt'
        saved = torch.load(original, map_location='cpu', weights_only=True)
        model = AudioClassifier(kind)
        model.load_state_dict(saved['state_dict'])
        # Keep the original train-only normalisation for a reproducible fine-tune.
        x = {s: [(v - saved['mean']) / saved['std'] for v in bags] for s, bags in inputs.items()}
        y = {s: torch.tensor([r['expected'] for r in rows], dtype=torch.float32) for s, rows in groups.items()}
        weight = (y['train'] == 0).sum() / (y['train'] == 1).sum()
        optimizer = torch.optim.Adam(model.parameters(), lr=.0003)

        def scores(split):
            model.eval()
            with torch.inference_mode():
                return [float(model(bag).softmax(-1)[:, 1].max()) for bag in x[split]]

        best = None
        history = []
        for epoch in range(0, 11):
            if epoch:
                model.train()
                order = torch.randperm(len(x['train'])).tolist()
                for offset in range(0, len(order), 16):
                    indices = order[offset:offset + 16]
                    bags = [x['train'][i] for i in indices]
                    optimizer.zero_grad()
                    logits = bag_logits(model(torch.cat(bags)), [len(b) for b in bags])
                    loss = F.binary_cross_entropy_with_logits(logits, y['train'][indices], pos_weight=weight)
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(model.parameters(), 5)
                    optimizer.step()
            probabilities = scores('validation')
            metric = max((binary_metrics(y['validation'], probabilities, t) for t in np.linspace(.05, .95, 19)),
                         key=lambda m: (m['f1'], m['precision'], m['threshold']))
            history.append({'epoch': epoch, **metric})
            if best is None or metric['f1'] > best['validation']['f1']:
                best = {'epoch': epoch, 'validation': metric, 'state': copy.deepcopy(model.state_dict())}
            print(f'{kind} epoch {epoch}: validation F1 {metric["f1"]:.3f}', flush=True)
        model.load_state_dict(best.pop('state'))
        threshold = best['validation']['threshold']
        checkpoint = OUTPUT / f'esc50_fsd_mil_{kind}.pt'
        torch.save({**saved, 'state_dict': model.state_dict(), 'threshold': threshold,
                    'training_source': 'ESC training + FSD official train selected subset, clip max MIL'}, checkpoint)
        evaluations = {}
        for split in ('test', 'fsd_test'):
            probabilities = scores(split)
            evaluations[split] = {'metrics': binary_metrics(y[split], probabilities, threshold),
                'records': [{'filename': r['filename'], 'sha256': r['sha256'], 'expected': r['expected'], 'score': p}
                            for r, p in zip(groups[split], probabilities)]}
        reports[kind] = {**best, 'validation_history': history, 'evaluations': evaluations,
                        'initial_checkpoint_sha256': hashlib.sha256(original.read_bytes()).hexdigest(),
                        'checkpoint_sha256': hashlib.sha256(checkpoint.read_bytes()).hexdigest()}
    report = {'seed': 20261011, 'models': reports, 'promoted': False,
              'counts': {s: len(r) for s, r in groups.items()},
              'protocol': '10 epochs + unchanged epoch 0; epoch and threshold by ESC validation F1 only; max-window MIL',
              'limitations': ['FSD weak negatives may omit Dog; no emotion/identity supervision',
                              'existing evaluation sets already inspected: development comparison, not new blind test',
                              'source IDs and exact hashes checked; transformed duplicates cannot be excluded',
                              'balanced selected FSD evaluation is not household prevalence',
                              'ESC validation has only a small number of Dog examples'],
              'manifests': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                            (ESC/'manifest.json', FSD/'dev_subset/manifest.json', FSD/'eval_subset/manifest.json')}}
    Path('docs/evidence/audio_mil_comparison.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: {s: v['metrics'] for s, v in r['evaluations'].items()} for k, r in reports.items()}), flush=True)


if __name__ == '__main__':
    main()
