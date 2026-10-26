"""The web app must carry its own fonts: the Flutter web engine cannot use system fonts and otherwise downloads them
from fonts.gstatic.com, so without internet (or with that host blocked) every text disappears."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'petmind_app'


class BundledWebFontTests(unittest.TestCase):
    def setUp(self):
        self.pubspec = (APP / 'pubspec.yaml').read_text(encoding='utf-8')

    def test_noto_sans_kr_is_registered_under_the_name_the_theme_falls_back_to(self):
        self.assertRegex(self.pubspec, r'(?m)^\s*-\s*family:\s*Noto Sans KR\s*$')
        self.assertIn("'Noto Sans KR'", (APP / 'lib' / 'genesis_theme.dart').read_text(encoding='utf-8'))

    def test_roboto_is_registered_so_the_engine_does_not_download_it_at_start_up(self):
        self.assertRegex(self.pubspec, r'(?m)^\s*-\s*family:\s*Roboto\s*$')

    def test_the_declared_font_files_exist_and_carry_all_hangul_syllables(self):
        assets = re.findall(r'asset:\s*(assets/fonts/\S+\.ttf)', self.pubspec)
        self.assertGreaterEqual(len(set(assets)), 2)          # regular and bold
        for asset in set(assets):
            path = APP / asset
            self.assertTrue(path.is_file(), asset)
            self.assertGreater(path.stat().st_size, 1_000_000, asset)   # a full Hangul subset, not an empty stub
        self.assertTrue((APP / 'assets' / 'fonts' / 'OFL.txt').is_file())   # the font license travels with the files


if __name__ == '__main__':
    unittest.main()
