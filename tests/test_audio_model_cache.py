import os
import torch
from pet_monitor.audio_lstm import AudioClassifier
from pet_monitor.audio_model_cache import get_audio_predictor


def test_checkpoint_replacement_invalidates_cache_without_timestamp_change(tmp_path):
    path = tmp_path/'model.pt'
    saved = {'state_dict': AudioClassifier('pooled').state_dict(), 'mean': torch.zeros(40),
             'std': torch.ones(40), 'kind': 'pooled', 'threshold': .5,
             'labels': ['other', 'dog'], 'sample_rate': 16000, 'window_s': 5}
    torch.save(saved, path)
    original = path.stat()
    first = get_audio_predictor(path)
    assert get_audio_predictor(path) is first
    saved['threshold'] = .8
    torch.save(saved, path)
    os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))
    updated = get_audio_predictor(path)
    assert updated is not first and updated.threshold == .8
