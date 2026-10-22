import unittest
from pathlib import Path

from scripts.seed_demo_records import classify, split_outings


class SeedDemoRecordsTests(unittest.TestCase):
    def test_classify_by_esc50_class_number(self):
        self.assertEqual(classify(Path('5-203128-A-0.wav'))[0], 'pet_vocalization')
        self.assertEqual(classify(Path('5-181766-A-10.wav'))[0], 'other')
        self.assertEqual(classify(Path('1-101336-A-30.wav'))[0], 'uncertain')
        self.assertEqual(classify(Path('unknown.wav'))[0], 'uncertain')

    def test_outings_separate_quiet_and_barking(self):
        files = [Path(n) for n in ('1-100032-A-0.wav', '5-181766-A-10.wav', '5-203128-A-0.wav')]
        plan = split_outings(files)
        self.assertEqual(len(plan), 2)
        self.assertEqual([f.name for f in plan[0][1]], ['5-181766-A-10.wav'])
        self.assertEqual(len(plan[1][1]), 2)

    def test_single_group_gives_single_outing(self):
        self.assertEqual(len(split_outings([Path('5-203128-A-0.wav')])), 1)
        self.assertEqual(split_outings([]), [])


if __name__ == '__main__':
    unittest.main()
