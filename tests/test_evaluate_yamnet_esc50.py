import unittest

from scripts.evaluate_yamnet_esc50 import wilson


class WilsonIntervalTests(unittest.TestCase):
    def test_all_hits_have_a_lower_bound_below_one_and_upper_bound_one(self):
        low, high = wilson(40, 40)
        self.assertAlmostEqual(low, 0.912, places=3)
        self.assertEqual(high, 1.0)

    def test_rare_events_stay_inside_zero_and_one(self):
        low, high = wilson(34, 1960)
        self.assertAlmostEqual(low, 0.0124, places=3)
        self.assertAlmostEqual(high, 0.0241, places=3)

    def test_zero_trials_is_safe(self):
        self.assertEqual(wilson(0, 0), (0.0, 0.0))


if __name__ == '__main__':
    unittest.main()
