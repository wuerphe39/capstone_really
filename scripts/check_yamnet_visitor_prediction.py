"""Apply the experimental embedding heads to the labeled demo scene."""
import json
from pathlib import Path

import numpy as np
import torch

from pet_monitor.yamnet_lstm import YamnetEmbeddingClassifier


ROOT = Path('artifacts/yamnet_bark_experiment')


def main():
    with np.load(ROOT/'visitor_scene.npz') as data:
        if int(data['version']) != 3:
            raise ValueError('visitor YAMNet features use an unsupported format')
        model_sha = str(data['model_sha256'])
        lengths = data['lengths'].astype(int)
        pieces = np.split(data['embeddings'].astype(np.float32), np.cumsum(lengths)[:-1])
        direct = data['scores'][:, 0].tolist()
    outcomes = {'yamnet_direct_bark': direct}
    for kind in ('pooled', 'lstm'):
        saved = torch.load(ROOT/f'yamnet_embedding_{kind}.pt', map_location='cpu', weights_only=True)
        if saved['yamnet_model_sha256'] != model_sha:
            raise ValueError('visitor YAMNet features came from a different model')
        model = YamnetEmbeddingClassifier(saved['kind'])
        model.load_state_dict(saved['state_dict'])
        model.eval()
        mean, std = saved['mean'].numpy(), saved['std'].numpy()
        width = saved['max_patches']
        x = torch.from_numpy(np.stack([
            np.pad((part-mean)/std, ((0, width-len(part)), (0, 0))) for part in pieces]))
        with torch.inference_mode():
            scores = torch.sigmoid(model(x, torch.tensor(lengths))).tolist()
        outcomes[kind] = {'window_scores': scores, 'threshold': saved['threshold'],
                          'candidates': [score >= saved['threshold'] for score in scores]}
    (ROOT/'visitor_predictions.json').write_text(json.dumps(outcomes, indent=2), encoding='utf-8')
    print(json.dumps(outcomes), flush=True)


if __name__ == '__main__':
    main()
