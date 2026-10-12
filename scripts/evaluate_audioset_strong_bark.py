"""Compare frozen Bark detectors against AudioSet's time-aligned eval labels.

No training or threshold selection occurs here. YAMNet was pretrained on
AudioSet, so the result diagnoses timing/errors rather than independent
generalization.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import torch

from pet_monitor.audio_lstm import binary_metrics
from pet_monitor.yamnet_lstm import YamnetEmbeddingClassifier
from scripts.train_audioset_bark_lstm import window_label


ROOT = Path('artifacts/audioset_bark_strong_eval')
TRAIN_ROOT = Path('artifacts/audioset_bark_strong')
BASE_ROOT = Path('artifacts/yamnet_bark_experiment')
CHECKPOINTS = {
    'embedding_lstm_original': BASE_ROOT/'yamnet_embedding_lstm.pt',
    'embedding_lstm_audioset_seed20261012': TRAIN_ROOT/'yamnet_embedding_lstm_audioset.pt',
    'embedding_lstm_audioset_seed11': TRAIN_ROOT/'yamnet_embedding_lstm_audioset_seed11.pt',
    'embedding_lstm_audioset_seed29': TRAIN_ROOT/'yamnet_embedding_lstm_audioset_seed29.pt',
}


def load_windows():
    path = ROOT/'manifest.json'
    manifest = json.loads(path.read_text(encoding='utf-8'))
    extraction = json.loads((ROOT/'extraction.json').read_text(encoding='utf-8'))
    if hashlib.sha256(path.read_bytes()).hexdigest() != extraction['manifest_sha256']:
        raise ValueError('eval manifest changed after feature extraction')
    train = json.loads((TRAIN_ROOT/'manifest.json').read_text(encoding='utf-8'))
    train_ids = {row['video_id'] for row in train['rows']['train']}
    train_hashes = {row['sha256'] for row in train['rows']['train']}
    if any(row['video_id'] in train_ids for row in manifest['rows']['eval']):
        raise ValueError('AudioSet video ID shared between train and eval')
    if any(row['sha256'] in train_hashes for row in manifest['rows']['eval']):
        raise ValueError('AudioSet WAV hash shared between train and eval')
    records = []
    for row in manifest['rows']['eval']:
        source = Path(row['path'])
        if hashlib.sha256(source.read_bytes()).hexdigest() != row['sha256']:
            raise ValueError(f'changed audio: {row["clip_id"]}')
        with np.load(ROOT/'features'/(row['sha256']+'.npz')) as data:
            if (int(data['version']) != 3 or
                    str(data['model_sha256']) != extraction['model_sha256']):
                raise ValueError(f'YAMNet mismatch: {row["clip_id"]}')
            pieces = np.split(data['embeddings'].astype(np.float32),
                              np.cumsum(data['lengths'].astype(int))[:-1])
            bark_scores = data['scores'][:, 0].astype(float).tolist()
        if len(pieces) != 2 or len(bark_scores) != 2:
            raise ValueError(f'expected two 5-second windows: {row["clip_id"]}')
        for index, (piece, score) in enumerate(zip(pieces, bark_scores)):
            overlap = sum(max(0, min((index+1)*5, end)-max(index*5, start))
                          for start, end in row['bark_intervals_s'])
            records.append({'clip_id': row['clip_id'], 'video_id': row['video_id'],
                            'window': index, 'label': window_label(row['bark_intervals_s'], index),
                            'bark_overlap_s': overlap, 'labels': row['labels'],
                            'yamnet_score': score, 'piece': piece})
    return records, extraction, manifest


def checkpoint_scores(records, checkpoint, model_sha):
    saved = torch.load(checkpoint, map_location='cpu', weights_only=True)
    if saved['yamnet_model_sha256'] != model_sha:
        raise ValueError(f'checkpoint YAMNet mismatch: {checkpoint}')
    mean, std = saved['mean'].numpy(), saved['std'].numpy()
    model = YamnetEmbeddingClassifier('lstm').eval()
    model.load_state_dict(saved['state_dict'])
    scores = []
    with torch.inference_mode():
        for row in records:
            piece = (row['piece']-mean)/std
            x = torch.from_numpy(piece[None, :, :])
            length = torch.tensor([len(piece)])
            scores.append(float(torch.sigmoid(model(x, length))[0]))
    return scores, float(saved['threshold'])


def evaluate(records, scores, threshold):
    labels = [row['label'] for row in records]
    window_metrics = binary_metrics(labels, scores, threshold)
    clips = {}
    for row, score in zip(records, scores):
        entry = clips.setdefault(row['clip_id'], {'label': 0, 'score': 0.0})
        entry['label'] = max(entry['label'], row['label'])
        entry['score'] = max(entry['score'], score)
    clip_metrics = binary_metrics([r['label'] for r in clips.values()],
                                  [r['score'] for r in clips.values()], threshold)
    errors = [{'clip_id': row['clip_id'], 'window': row['window'],
               'label': row['label'], 'score': round(score, 5),
               'bark_overlap_s': round(row['bark_overlap_s'], 3),
               'other_labels': [name for name in row['labels'] if name != '/m/05tny_']}
              for row, score in zip(records, scores)
              if (score >= threshold) != bool(row['label'])]
    return {'threshold': threshold, 'window': window_metrics, 'clip': clip_metrics,
            'errors': errors}


def train_threshold_diagnostic():
    train = json.loads((TRAIN_ROOT/'manifest.json').read_text(encoding='utf-8'))
    labels, scores = [], []
    for row in train['rows']['train']:
        with np.load(TRAIN_ROOT/'features'/(row['sha256']+'.npz')) as data:
            bark = data['scores'][:, 0].astype(float)
        if len(bark) != 2:
            raise ValueError(f'expected two train windows: {row["clip_id"]}')
        for index, score in enumerate(bark):
            labels.append(window_label(row['bark_intervals_s'], index))
            scores.append(float(score))
    return {str(threshold): binary_metrics(labels, scores, threshold)
            for threshold in (.01, .02, .05)}


def main():
    torch.set_num_threads(2)
    records, extraction, manifest = load_windows()
    baseline = json.loads((BASE_ROOT/'comparison.json').read_text(encoding='utf-8'))
    direct_scores = [row['yamnet_score'] for row in records]
    comparisons = {'yamnet_direct': evaluate(records, direct_scores,
                   baseline['comparison']['yamnet_bark']['threshold'])}
    for name, checkpoint in CHECKPOINTS.items():
        scores, threshold = checkpoint_scores(records, checkpoint,
                                              extraction['model_sha256'])
        comparisons[name] = evaluate(records, scores, threshold)
    report = {
        'scope': 'AudioSet strong eval: time-aligned diagnostic, not independent YAMNet test',
        'source': manifest['source'],
        'counts': {'clips': len(manifest['rows']['eval']), 'windows': len(records),
                   'bark_windows': sum(row['label'] for row in records),
                   'non_bark_windows': sum(not row['label'] for row in records),
                   'short_bark_windows_lt_1s': sum(row['label'] and row['bark_overlap_s'] < 1
                                                  for row in records)},
        'short_bark_diagnostic': {
            name: {'missed_lt_1s': sum(error['label'] and error['bark_overlap_s'] < 1
                                      for error in item['errors']),
                   'missed_ge_1s': sum(error['label'] and error['bark_overlap_s'] >= 1
                                      for error in item['errors'])}
            for name, item in comparisons.items()},
        'train_only_yamnet_threshold_diagnostic': train_threshold_diagnostic(),
        'comparison': comparisons,
        'limitations': ['YAMNet backbone pretrained on AudioSet',
                        'YouTube availability creates a selected subset',
                        '5-second window labels are projected from finer intervals',
                        'Thresholds fixed on FSD validation, not tuned on AudioSet eval'],
    }
    (ROOT/'comparison.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'counts': report['counts'],
                      'comparison': {name: {'window': item['window'], 'clip': item['clip']}
                                     for name, item in comparisons.items()}},
                     ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
