import numpy as np
import pytest
import soundfile as sf
import torch

from scripts.train_audio_mil import assert_disjoint, bag_logits, features


def test_positive_bag_does_not_label_every_window_positive():
    logits = torch.tensor([[4., 0.], [0., 3.], [2., 0.]], requires_grad=True)
    values = bag_logits(logits, [2, 1])
    assert values.tolist() == [3., -2.]
    (-values[0]).backward()
    assert logits.grad[0].abs().sum() == 0
    assert logits.grad[1].abs().sum() > 0
    with pytest.raises(ValueError):
        bag_logits(logits, [1])


def test_features_include_sound_after_first_five_seconds(tmp_path):
    path = tmp_path/'late.wav'
    audio = np.zeros(16000 * 6, dtype=np.float32)
    audio[80000:] = .1 * np.sin(np.arange(16000) * 2 * np.pi * 440 / 16000)
    sf.write(path, audio, 16000)
    result = features(path)
    assert result.shape == (2, 251, 40)
    assert result[1].max() > result[0].max()


@pytest.mark.parametrize('key', ['source_id', 'sha256'])
def test_overlap_rejected_even_with_different_other_identifier(key):
    left = {'source_id': 'a', 'sha256': 'x'}
    right = {'source_id': 'b', 'sha256': 'y', key: left[key]}
    with pytest.raises(ValueError, match=key):
        assert_disjoint([left], [right])
