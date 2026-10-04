import unittest

import numpy as np

from pet_monitor import BarkDetector, Observation, build_context, classify_window
from pet_monitor.simulator import SAMPLE_RATE, make_audio, make_scenario, make_trajectory


def stream(det, audio, chunk=SAMPLE_RATE // 2):
    for i in range(0, len(audio), chunk):
        det.feed(audio[i:i + chunk])


class BarkTests(unittest.TestCase):
    def test_silence_has_no_bark(self):
        det = BarkDetector()
        stream(det, make_audio(30, []))
        s = det.summarize(30)
        self.assertEqual((s.count, s.level, s.peak_db), (0, "none", None))

    def test_counts_known_barks(self):
        times = [2.0, 4.0, 6.5, 9.0, 15.0]
        det = BarkDetector()
        stream(det, make_audio(30, times))
        s = det.summarize(30)
        self.assertEqual(s.count, len(times))
        self.assertEqual(s.level, "frequent")
        self.assertGreater(s.peak_db, -30)
        for ev, t in zip(det.events, times):
            self.assertAlmostEqual(ev.start_s, t, delta=0.1)

    def test_chunk_size_does_not_change_result(self):
        audio = make_audio(30, [3.0, 3.6, 10.0])
        a, b = BarkDetector(), BarkDetector()
        stream(a, audio, chunk=SAMPLE_RATE // 2)
        stream(b, audio, chunk=777)  # 프레임 경계와 맞지 않는 크기
        self.assertEqual(a.summarize(30).count, b.summarize(30).count)

    def test_sustained_noise_is_not_bark(self):
        audio = make_audio(10, [])
        audio[3 * SAMPLE_RATE:6 * SAMPLE_RATE] += np.random.default_rng(1).normal(0, 0.1, 3 * SAMPLE_RATE).astype(np.float32)
        det = BarkDetector()
        stream(det, audio)
        self.assertEqual(det.summarize(10).count, 0)

    def test_single_frame_click_ignored(self):
        audio = make_audio(5, [])
        audio[SAMPLE_RATE:SAMPLE_RATE + 200] += 0.5
        det = BarkDetector()
        stream(det, audio)
        self.assertEqual(det.summarize(5).count, 0)

    def test_window_only_counts_recent(self):
        det = BarkDetector()
        stream(det, make_audio(60, [5.0, 50.0]))
        self.assertEqual(det.summarize(30).count, 1)


class MotionTests(unittest.TestCase):
    def check(self, kind, expected, seeds=range(5)):
        for seed in seeds:
            obs = make_trajectory(kind, 10, seed=seed)
            self.assertEqual(classify_window(obs), expected, f"{kind} seed={seed}")

    def test_still(self):
        self.check("still", "still")

    def test_moving(self):
        self.check("moving", "moving")

    def test_spinning(self):
        self.check("spinning", "spinning")

    def test_pacing(self):
        self.check("pacing", "pacing")

    def test_sit_stand_repeat(self):
        self.check("sit_stand_repeat", "sit_stand_repeat")

    def test_too_few_observations_is_unknown(self):
        self.assertEqual(classify_window([Observation(0, 0.5, 0.5)] * 3), "unknown")


class ContextTests(unittest.TestCase):
    def build(self, name):
        audio, obs = make_scenario(name)
        det = BarkDetector()
        stream(det, audio)
        return build_context(det, obs)

    def test_calm(self):
        ctx = self.build("calm")
        self.assertEqual(ctx.bark.count, 0)
        self.assertEqual(ctx.motion.dominant, "still")
        self.assertIn("짖지 않았다", ctx.to_text())

    def test_anxious(self):
        ctx = self.build("anxious")
        self.assertEqual(ctx.bark.count, 8)
        self.assertEqual(ctx.motion.dominant, "spinning")
        self.assertAlmostEqual(sum(ctx.motion.seconds_by_label.values()), 30.0, places=3)
        self.assertIn("제자리 회전", ctx.to_text())

    def test_bored_pacing(self):
        ctx = self.build("bored_pacing")
        self.assertEqual(ctx.bark.count, 2)
        self.assertEqual(ctx.bark.level, "occasional")
        self.assertEqual(ctx.motion.dominant, "pacing")


if __name__ == "__main__":
    unittest.main()
