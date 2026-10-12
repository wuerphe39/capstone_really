import pytest

pytest.importorskip('torch')
pytest.importorskip('ultralytics')

from scripts.evaluate_tigdog import classification_metrics, frame_reference
from scripts.measure_lstm_real import clustered_change_ci
import numpy as np


def test_unannotated_or_incompatible_behavior_never_becomes_negative():
    assert frame_reference([]) is None
    assert frame_reference([14]) is None  # skateboard motion is incompatible with still references
    assert frame_reference([3]) is None  # turning is not repeated spinning
    assert frame_reference([1, 2]) == 'locomotion'
    assert frame_reference([9, 10]) == 'non_locomotion'


def test_unknown_predictions_count_as_failures_and_coverage_is_separate():
    rows = [{'expected': 'non_locomotion', 'result': 'unknown'},
            {'expected': 'locomotion', 'result': 'locomotion'},
            {'expected': 'non_locomotion', 'result': 'locomotion'}]
    result = classification_metrics(rows, 'result')
    assert result['accuracy'] == pytest.approx(1/3)
    assert result['coverage'] == pytest.approx(2/3)
    assert result['accepted_accuracy'] == .5
    assert result['macro_f1'] == pytest.approx(1/3)
    assert result['confusion_matrix'] == [[0, 1, 1], [0, 1, 0]]
    assert classification_metrics([], 'result')['accuracy'] is None
    assert classification_metrics(rows[1:2], 'result')['macro_f1'] is None


def test_cluster_bootstrap_uses_recording_groups_not_correlated_frames():
    old = np.array([1., 1., 2.]); new = np.array([.5, .5, 1.])
    result = clustered_change_ci(old, new, np.array(['one', 'one', 'two']))
    assert result['families'] == 2
    assert result['equal_family_error_reduction_percent'] == 50
    assert result['percentile_95_ci'] == [50, 50]
