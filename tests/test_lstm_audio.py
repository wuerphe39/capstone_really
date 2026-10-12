from pathlib import Path

import numpy as np
import pytest

pytest.importorskip('torch')
pytest.importorskip('soundfile')
import soundfile as sf

from pet_monitor.audio import analyze_wav
from pet_monitor.bark import BarkDetector
from pet_monitor.lstm import LSTMPredictor
from pet_monitor.simulator import make_audio, make_trajectory


def test_file_ending_candidate_finalized_once_without_clock_drift():
    detector = BarkDetector()
    detector.feed(make_audio(2, [1.8], bark_len_s=.2))
    end = detector.now_s
    detector.finish()
    count = len(detector.events)
    detector.finish()
    assert detector.now_s == end and len(detector.events) == count
    assert count == 1


def test_wav_resampling_stereo_and_empty_input(tmp_path):
    audio = make_audio(3, [1])
    path = tmp_path / 'stereo.wav'
    sf.write(path, np.column_stack([audio, audio]), 16000)
    result = analyze_wav(path)
    assert result['context']['bark']['count'] == 1
    assert result['context']['motion']['dominant'] == 'unknown'
    assert result['original_channels'] == 2
    # Same waveform sampled at double rate by repeating: still one event.
    sf.write(path, np.repeat(audio, 2), 32000)
    assert analyze_wav(path)['context']['bark']['count'] == 1
    sf.write(path, np.zeros(0), 16000)
    with pytest.raises(ValueError):
        analyze_wav(path)


def test_checkpoint_reload_and_tracking_gaps():
    path = Path('artifacts/lstm/trajectory_lstm.pt')
    if not path.exists():
        pytest.skip('Run python -m scripts.train_lstm first')
    predictor = LSTMPredictor(path)
    for label in ['still', 'moving', 'spinning', 'pacing']:
        observations = make_trajectory(label, 10)
        assert predictor.predict(observations)['label'] == label
        assert predictor.predict(observations[:20])['label'] == 'unknown'
        short_missing = observations[:24] + observations[26:]
        result = predictor.predict(short_missing)
        assert result['label'] == label
        assert result['interpolated_missing_samples'] == 2
        observations[25].t += 1
        assert predictor.predict(observations)['label'] == 'unknown'
