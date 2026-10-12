import unittest

from scripts.yamnet_live_demo import BarkEventTracker, bar, mmss


def run(scores, **kw):
    tr = BarkEventTracker(**kw)
    events = []
    for i, s in enumerate(scores):
        events += tr.feed(i * 0.5, s)
    return events + tr.finish()


class BarkEventTrackerTests(unittest.TestCase):
    def test_no_events_below_threshold(self):
        self.assertEqual(run([0.0, 0.01, 0.04, 0.0]), [])

    def test_single_event_start_and_end(self):
        ev = run([0, 0, 0.3, 0.8, 0.2, 0, 0, 0])
        self.assertEqual([e.kind for e in ev], ["start", "end"])
        self.assertEqual(ev[0].t, 1.0)
        self.assertAlmostEqual(ev[1].peak, 0.8)
        self.assertAlmostEqual(ev[1].duration, 1.5)  # 1.0~2.0초 + 간격 0.5

    def test_short_dip_keeps_one_event(self):
        ev = run([0.3, 0.01, 0.3, 0, 0, 0], hold=2)
        self.assertEqual([e.kind for e in ev], ["start", "end"])

    def test_two_separate_events(self):
        ev = run([0.3, 0, 0, 0, 0.4, 0, 0])
        self.assertEqual([e.kind for e in ev], ["start", "end", "start", "end"])

    def test_event_open_at_stream_end_is_closed(self):
        ev = run([0, 0.5, 0.6])
        self.assertEqual([e.kind for e in ev], ["start", "end"])

    def test_invalid_config(self):
        with self.assertRaises(ValueError):
            BarkEventTracker(threshold=0)
        with self.assertRaises(ValueError):
            BarkEventTracker(hold=0)


class FormatTests(unittest.TestCase):
    def test_bar_and_time(self):
        self.assertEqual(bar(0.5, 10), "#####.....")
        self.assertEqual(bar(2.0, 4), "####")
        self.assertEqual(mmss(65.5), "01:05.5")


if __name__ == "__main__":
    unittest.main()
