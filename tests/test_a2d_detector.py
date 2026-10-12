import numpy as np
import pytest

from pet_monitor.video import dog_class_id
from pet_monitor.detection import unique_dog_indices
from scripts.train_a2d_detector import measures


def test_dog_class_is_found_in_coco_and_one_class_detector():
    assert dog_class_id({0: 'person', 16: 'dog'}) == 16
    assert dog_class_id({0: 'dog'}) == 0
    with pytest.raises(ValueError):
        dog_class_id({0: 'person'})


def test_detector_evaluation_does_not_count_duplicate_box_as_second_dog():
    dog = np.array([10, 10, 50, 50], dtype=float)
    records = [([dog], np.stack([dog, dog]), np.array([.9, .8]))]
    result = measures(records, .5)
    assert (result['tp'], result['fp'], result['fn']) == (1, 1, 0)


def test_contained_partial_dog_box_is_suppressed_but_separate_dog_is_kept():
    boxes = np.array([[8, 0, 430, 284], [0, 1, 185, 198], [440, 5, 530, 145]], dtype=float)
    kept = unique_dog_indices(boxes, [.84, .15, .7])
    assert kept == [0, 2]
