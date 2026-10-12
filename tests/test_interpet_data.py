import numpy as np
import pytest

pytest.importorskip('torch')
from scripts.prepare_interpet import build_windows


def test_native_frame_time_is_preserved_and_segment_gaps_not_bridged():
    frames = np.arange(0, 1200, 2)
    root = np.column_stack([frames/60, np.zeros(len(frames)), np.ones(len(frames))])
    quality = np.ones(len(frames)); residual = np.full(len(frames), 10.)
    windows, starts = build_windows(root, frames, [[0, 600]], quality, residual, 60)
    assert len(windows) == 2 and starts == [0., 10.]
    assert windows[0][-1, 0] == pytest.approx(9.8)
    assert windows[1][-1, 0] == pytest.approx(19.8)
    assert build_windows(root, frames, [[0, 290], [290, 580]], quality, residual, 60)[0] == []


def test_bad_pose_quality_is_excluded_instead_of_becoming_training_truth():
    frames = np.arange(0, 600, 2); root = np.zeros((len(frames), 3))
    quality = np.ones(len(frames)); reprojection = np.full(len(frames), 10.)
    quality[:80] = 0
    assert build_windows(root, frames, [[0, len(frames)]], quality, reprojection, 60)[0] == []
    with pytest.raises(ValueError):
        build_windows(root, frames[::-1], [[0, len(frames)]], quality, reprojection, 60)
