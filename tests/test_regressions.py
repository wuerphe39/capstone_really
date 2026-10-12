import unittest
import numpy as np

from pet_monitor import BarkConfig, BarkDetector, MotionConfig, build_context
from pet_monitor.motion import summarize_motion
from pet_monitor.simulator import SAMPLE_RATE, make_audio, make_trajectory


class RegressionTests(unittest.TestCase):
    def test_sustained_noise_tail_is_not_a_bark(self):
        for duration in (1.6, 2.0, 2.5, 3.0, 3.2, 4.0):
            with self.subTest(duration=duration):
                audio = make_audio(10, [])
                size = int(duration * SAMPLE_RATE)
                audio[SAMPLE_RATE:SAMPLE_RATE + size] += np.random.default_rng(42).normal(0, .1, size)
                detector = BarkDetector()
                detector.feed(audio)
                self.assertEqual(detector.summarize(10).count, 0)

    def test_rearms_after_noise_and_detects_later_bark(self):
        audio = make_audio(12, [9.0])
        audio[SAMPLE_RATE:5*SAMPLE_RATE] += np.random.default_rng(42).normal(0, .1, 4*SAMPLE_RATE)
        detector = BarkDetector()
        for i in range(0, len(audio), 777):
            detector.feed(audio[i:i+777])
        self.assertEqual(detector.summarize(12).count, 1)
        self.assertAlmostEqual(detector.events[0].start_s, 9, delta=.1)

    def test_stale_motion_is_unknown_on_audio_timeline(self):
        detector = BarkDetector()
        detector.feed(make_audio(60, []))
        context = build_context(detector, make_trajectory('pacing', 30))
        self.assertEqual(context.motion.dominant, 'unknown')
        self.assertNotIn('pacing', context.motion.seconds_by_label)

    def test_missing_motion_is_not_stretched(self):
        summary = summarize_motion(make_trajectory('pacing', 10, t0=20), 30, end_s=30)
        self.assertGreater(summary.seconds_by_label.get('unknown', 0), 0)
        self.assertLess(summary.seconds_by_label.get('pacing', 0), 30)
        self.assertAlmostEqual(sum(summary.seconds_by_label.values()), 30)

    def test_invalid_settings_fail_without_looping_or_dividing(self):
        for values in ({'sample_rate': 0}, {'frame_ms': 0}, {'max_event_s': float('nan')}):
            with self.assertRaises(ValueError):
                BarkConfig(**values)
        for values in ({'stride_s': 0}, {'window_s': float('inf')}, {'min_obs': 1}):
            with self.assertRaises(ValueError):
                MotionConfig(**values)
        with self.assertRaises(ValueError):
            summarize_motion([], window_s=0)

    def test_invalid_audio_does_not_advance_detector(self):
        detector = BarkDetector()
        for samples in (np.zeros((20, 2)), np.array([float('nan')])):
            with self.assertRaises(ValueError):
                detector.feed(samples)
        self.assertEqual(detector.now_s, 0)


if __name__ == '__main__':
    unittest.main()
