"""Train a patch-supervised temporal LSTM on AudioSet strong train labels.

This is an isolated candidate, not the application model. Model/threshold
selection uses only a video-disjoint subset of AudioSet strong train.
"""
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from pet_monitor.audio_lstm import binary_metrics


TRAIN_ROOT = Path('artifacts/audioset_bark_strong')
EVAL_ROOT = Path('artifacts/audioset_bark_strong_eval')
SEED = 20261012
PATCH_S = .96
HOP_S = .48


def patch_labels(intervals, count):
    return np.array([int(sum(max(0, min(i*HOP_S+PATCH_S, end)-max(i*HOP_S, start))
                             for start, end in intervals) >= .1)
                     for i in range(count)], dtype=np.float32)


def load(root, split):
    manifest_path = root/'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    extraction = json.loads((root/'patch_extraction.json').read_text(encoding='utf-8'))
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != extraction['manifest_sha256']:
        raise ValueError('manifest changed after patch extraction')
    rows = []
    for row in manifest['rows'][split]:
        with np.load(root/'patch_features'/(row['sha256']+'.npz')) as data:
            if (str(data['model_sha256']) != extraction['model_sha256'] or
                    int(data['version']) != 1):
                raise ValueError(f'incompatible patch features: {row["clip_id"]}')
            embeddings = data['embeddings'].astype(np.float32)
            bark_scores = data['bark_scores'].astype(np.float32)
        if len(embeddings) != 20 or len(bark_scores) != 20:
            raise ValueError(f'expected 20 patches: {row["clip_id"]}')
        rows.append({**row, 'x': embeddings, 'patch_y': patch_labels(row['bark_intervals_s'], 20),
                     'bark_scores': bark_scores})
    return rows, extraction


def windows(rows, score_key):
    labels, scores, meta = [], [], []
    for row in rows:
        for index in (0, 1):
            center = np.arange(20)*HOP_S + PATCH_S/2
            which = (center >= index*5) & (center < (index+1)*5)
            overlap = sum(max(0, min((index+1)*5, end)-max(index*5, start))
                          for start, end in row['bark_intervals_s'])
            labels.append(int(overlap >= .1))
            scores.append(float(np.max(row[score_key][which])))
            meta.append({'clip_id': row['clip_id'], 'window': index,
                         'bark_overlap_s': overlap})
    return labels, scores, meta


class PatchLSTM(nn.Module):
    def __init__(self):
        super().__init__()
        self.project = nn.Sequential(nn.Linear(1024, 64), nn.LayerNorm(64), nn.Tanh(),
                                     nn.Dropout(.2))
        self.temporal = nn.LSTM(64, 32, bidirectional=True, batch_first=True)
        self.head = nn.Linear(64, 1)

    def forward(self, x):
        hidden, _ = self.temporal(self.project(x))
        return self.head(hidden).squeeze(-1)


def predict(model, rows, mean, std):
    model.eval()
    with torch.inference_mode():
        x = torch.tensor(np.stack([(row['x']-mean)/std for row in rows]))
        scores = torch.sigmoid(model(x)).numpy()
    for row, score in zip(rows, scores):
        row['patch_lstm_scores'] = score


def main():
    torch.set_num_threads(2)
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    all_train, train_extraction = load(TRAIN_ROOT, 'train')
    evaluation, eval_extraction = load(EVAL_ROOT, 'eval')
    if train_extraction['model_sha256'] != eval_extraction['model_sha256']:
        raise ValueError('YAMNet checkpoint differs between train and eval')
    if ({r['video_id'] for r in all_train} & {r['video_id'] for r in evaluation} or
            {r['sha256'] for r in all_train} & {r['sha256'] for r in evaluation}):
        raise ValueError('train/eval source overlap')
    order = sorted(all_train, key=lambda row: hashlib.sha256(
        (str(SEED)+row['video_id']).encode()).hexdigest())
    validation, training = order[:16], order[16:]
    if not any(r['patch_y'].any() for r in validation) or not any(r['patch_y'].any() for r in training):
        raise ValueError('missing Bark patch in training or validation')
    patches = np.concatenate([row['x'] for row in training])
    mean = patches.mean(0)
    std = np.maximum(patches.std(0), .05)
    x = torch.tensor(np.stack([(row['x']-mean)/std for row in training]))
    y = torch.tensor(np.stack([row['patch_y'] for row in training]))
    pos_weight = torch.tensor(float((y == 0).sum()/(y == 1).sum()))
    direct_y, direct_scores, _ = windows(validation, 'bark_scores')
    direct_val = binary_metrics(direct_y, direct_scores, .05)
    max_fpr = min(.25, direct_val['false_positive_rate']+.05)
    model = PatchLSTM()
    optimizer = torch.optim.AdamW(model.parameters(), lr=.0005, weight_decay=.01)
    best = None
    history = []
    for epoch in range(1, 16):
        model.train()
        losses = []
        for indices in torch.randperm(len(training)).split(8):
            logits = model(x[indices])
            loss = F.binary_cross_entropy_with_logits(logits, y[indices],
                                                      pos_weight=pos_weight)
            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 5)
            optimizer.step()
            losses.append(float(loss.detach()))
        predict(model, validation, mean, std)
        labels, scores, _ = windows(validation, 'patch_lstm_scores')
        choices = [binary_metrics(labels, scores, float(threshold))
                   for threshold in np.arange(.05, .96, .05)]
        choices = [choice for choice in choices if choice['false_positive_rate'] <= max_fpr]
        if choices:
            choice = max(choices, key=lambda item: (item['f1'], item['precision']))
            history.append({'epoch': epoch, 'loss': float(np.mean(losses)), 'val': choice})
            if best is None or choice['f1'] > best['val']['f1']:
                best = {'epoch': epoch, 'state': copy.deepcopy(model.state_dict()), 'val': choice}
        print(f'epoch={epoch} val_f1={choices and choice["f1"]}', flush=True)
    if best is None:
        raise ValueError('no validation threshold meets FPR limit')
    model.load_state_dict(best['state'])
    predict(model, evaluation, mean, std)
    eval_y, eval_scores, meta = windows(evaluation, 'patch_lstm_scores')
    direct_eval_y, direct_eval_scores, _ = windows(evaluation, 'bark_scores')
    threshold = best['val']['threshold']
    candidate = binary_metrics(eval_y, eval_scores, threshold)
    direct = binary_metrics(direct_eval_y, direct_eval_scores, .05)
    if eval_y != direct_eval_y:
        raise ValueError('evaluation labels differ')
    report = {'scope': 'AudioSet strong train split to train/val; strong eval diagnostic only',
              'counts': {'training_clips': len(training), 'validation_clips': len(validation),
                         'evaluation_clips': len(evaluation),
                         'train_positive_patches': int(y.sum()), 'train_patches': int(y.numel())},
              'selection': {'max_validation_fpr': max_fpr, 'epoch': best['epoch'],
                            'threshold': threshold, 'validation': best['val']},
              'evaluation': {'patch_lstm': candidate, 'yamnet_direct': direct},
              'short_bark_misses': {
                  'patch_lstm_lt_1s': sum(label and item['bark_overlap_s'] < 1 and score < threshold
                                         for label, item, score in zip(eval_y, meta, eval_scores)),
                  'yamnet_direct_lt_1s': sum(label and item['bark_overlap_s'] < 1 and score < .05
                                             for label, item, score in zip(eval_y, meta, direct_eval_scores))},
              'limitations': ['YAMNet pretrained on AudioSet',
                              '64 obtainable training clips; train/val small',
                              'AudioSet eval was already analyzed in prior experiment',
                              'No independent household test'],
              'promoted': False}
    torch.save({'state_dict': model.state_dict(), 'mean': torch.tensor(mean),
                'std': torch.tensor(std), 'threshold': threshold,
                'yamnet_model_sha256': train_extraction['model_sha256']},
               TRAIN_ROOT/'patch_lstm.pt')
    (TRAIN_ROOT/'patch_lstm_comparison.json').write_text(
        json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
