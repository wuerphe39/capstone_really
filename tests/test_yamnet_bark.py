from pathlib import Path

import torch

from pet_monitor.yamnet_lstm import YamnetEmbeddingClassifier
from scripts.prepare_yamnet_bark_experiment import selected_rows


def test_explicit_bark_split_excludes_dog_only_and_esc_dog(tmp_path):
    grouped = {}
    for split, fsd, esc in [('train','fsd_train','esc_train'),
                            ('val','fsd_val','esc_val'), ('eval','fsd_eval','esc_test')]:
        def row(name, labels, expected, source):
            return {'source_id': name, 'labels': labels, 'expected': expected,
                    'sha256': (name*64)[:64], 'path': tmp_path/(name+'.wav'),
                    'split': split, 'category': source}
        grouped[fsd] = [row(split+'b', ['Dog','Bark'], 1, 'dog'),
                        row(split+'d', ['Dog'], 1, 'dog'),
                        row(split+'n', ['Speech'], 0, 'other')]
        grouped[esc] = [row(split+'e', [], 1, 'dog'),
                        row(split+'o', [], 0, 'other')]
    selected = selected_rows(grouped)
    for items in selected.values():
        assert len(items) == 3
        assert sum(item['label'] for item in items) == 1
        assert not any(item['source_id'].endswith(('d','e')) for item in items)


def test_pooled_embedding_head_ignores_padding():
    torch.manual_seed(7)
    model = YamnetEmbeddingClassifier('pooled').eval()
    data = torch.randn(1, 5, 1024)
    data[:, 3:] = 0
    longer = data.clone()
    longer[:, 3:] = 100
    with torch.inference_mode():
        assert torch.allclose(model(data, torch.tensor([3])),
                              model(longer, torch.tensor([3])))
