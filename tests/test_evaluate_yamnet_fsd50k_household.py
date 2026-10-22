import unittest

from scripts.evaluate_yamnet_fsd50k_household import bucket
from scripts.prepare_fsd50k_household import FORBIDDEN_NEGATIVE, GROUPS


class ClipLengthBucketTests(unittest.TestCase):
    def test_boundaries_are_half_open(self):
        self.assertEqual(bucket(0.3), '<1 s')
        self.assertEqual(bucket(0.999), '<1 s')
        self.assertEqual(bucket(1.0), '1-3 s')
        self.assertEqual(bucket(2.999), '1-3 s')
        self.assertEqual(bucket(3.0), '>=3 s')
        self.assertEqual(bucket(30.0), '>=3 s')


class NegativeSelectionRulesTests(unittest.TestCase):
    def test_dog_and_bark_labels_can_never_define_a_negative_group(self):
        for group, labels, cap in GROUPS:
            self.assertFalse(labels & FORBIDDEN_NEGATIVE, group)
            self.assertGreater(cap, 0)

    def test_group_names_are_unique(self):
        names = [g for g, _, _ in GROUPS]
        self.assertEqual(len(names), len(set(names)))


if __name__ == '__main__':
    unittest.main()
