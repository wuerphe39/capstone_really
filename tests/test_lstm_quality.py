import numpy as np
import pytest

torch = pytest.importorskip('torch')
from pet_monitor.lstm import FRAMES, LABELS, LSTMPredictor, TrajectoryLSTM, features
from pet_monitor.motion import Observation
from pet_monitor.simulator import make_trajectory
from scripts.prepare_mocap import read_root, recording_group


def test_low_confidence_and_track_jump_rejected(tmp_path):
    model = TrajectoryLSTM(8)
    for parameter in model.parameters():
        torch.nn.init.zeros_(parameter)
    path = tmp_path / 'ambiguous.pt'
    torch.save({'state_dict': model.state_dict(), 'labels': list(LABELS), 'frames': FRAMES,
                'feature_version': 2}, path)
    predictor = LSTMPredictor(path)
    result = predictor.predict(make_trajectory('still', 10))
    assert result['label'] == 'unknown' and result['confidence'] == .25
    assert len(result['probabilities']) == 4
    track = [Observation(i/5, .1 if i < 25 else .9, .5) for i in range(50)]
    assert 'track jump' in predictor.predict(track)['reason']


def test_tracking_coverage_uses_time_grid_with_faster_tracker(tmp_path):
    model = TrajectoryLSTM(8)
    path = tmp_path / 'coverage.pt'
    torch.save({'state_dict': model.state_dict(), 'labels': list(LABELS),
                'frames': FRAMES, 'feature_version': 2}, path)
    predictor = LSTMPredictor(path)
    dense = [Observation(i/15, .5, .5) for i in range(148)]
    assert predictor.predict(dense)['reason'] != 'less than 80% tracking coverage'
    # Many detections clustered into a few instants cannot impersonate 80%
    # coverage of the ten-second inference window.
    sparse_times = [float(base + offset) for base in np.arange(0, 9.61, .6)
                    for offset in (0, .02, .04, .06)] + [9.8]
    sparse = [Observation(t, .5, .5) for t in sparse_times]
    assert len(sparse) > 40
    assert predictor.predict(sparse)['reason'] == 'less than 80% tracking coverage'


def test_v2_features_finite_translation_invariant():
    coords = np.array([[o.cx, o.cy] for o in make_trajectory('spinning', 10)])
    actual = features(coords, 2)
    assert actual.shape == (50, 8) and np.isfinite(actual).all()
    np.testing.assert_allclose(actual, features(coords+.1, 2), atol=2e-5)
    assert features(coords, 1).shape == (50, 4)


def test_mocap_corruption_and_recording_identity():
    assert recording_group('D1_047z_KAN01_003.bvh') == recording_group('D1_047_KAN01_001.bvh')
    content = b'HIERARCHY\nROOT Hips\n{\nCHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation\n}\nMOTION\nFrames: 2\nFrame Time: 0.2\n1 2 3 0 0 0\n4 5 6 0 0 0\n'
    coords, dt = read_root(content)
    np.testing.assert_equal(coords, [[1, 3], [4, 6]])
    assert dt == .2
    with pytest.raises(ValueError):
        read_root(content.replace(b'Frames: 2', b'Frames: 3'))
    with pytest.raises(ValueError):
        read_root(content.replace(b'1 2 3', b'nan 2 3'))
