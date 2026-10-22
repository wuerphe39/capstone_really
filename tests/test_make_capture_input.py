import unittest

from scripts.make_capture_input import build_args, choose, parse_devices

SAMPLE = '''[dshow @ 000001] DirectShow video devices (some may be both video and audio devices)
[dshow @ 000001]  "OBS Virtual Camera" (none)
[dshow @ 000001]  "720p HD Camera" (video)
[dshow @ 000001] DirectShow audio devices
[dshow @ 000001]  "마이크(G435 Wireless Gaming Headset)" (audio)
[dshow @ 000001]  "마이크 배열(디지털 마이크용 인텔® 스마트 사운드 기술)" (audio)
'''


class CaptureInputTests(unittest.TestCase):
    def test_parse_ignores_alternative_names_and_none_kind(self):
        d = parse_devices(SAMPLE)
        self.assertEqual(d['video'], ['720p HD Camera'])
        self.assertEqual(len(d['audio']), 2)

    def test_default_choice_prefers_mic_array_and_skips_virtual_camera(self):
        d = parse_devices(SAMPLE + ' "OBS Virtual Camera" (video)\n')
        video, audio = choose(d)
        self.assertEqual(video, '720p HD Camera')
        self.assertIn('마이크 배열', audio)

    def test_explicit_choice_by_substring(self):
        _, audio = choose(parse_devices(SAMPLE), audio='g435')
        self.assertIn('G435', audio)

    def test_unknown_explicit_device_exits(self):
        with self.assertRaises(SystemExit):
            choose(parse_devices(SAMPLE), audio='nonexistent')

    def test_no_camera_exits_with_hint(self):
        with self.assertRaises(SystemExit):
            choose({'video': [], 'audio': ['mic']})

    def test_ffmpeg_args_order_matches_maps(self):
        a = build_args('cam', 'mic')
        self.assertEqual(a[a.index('-i') + 1], 'video=cam')
        self.assertEqual(a[len(a) - 1], 'audio=mic')


if __name__ == '__main__':
    unittest.main()


from scripts.make_capture_input import choose_mode, mode_args, parse_modes

WEBCAM = '''[dshow @ 0] DirectShow video device options (from video devices)
[dshow @ 0]   vcodec=mjpeg  min s=640x480 fps=30 max s=640x480 fps=30
[dshow @ 0]   vcodec=mjpeg  min s=1280x720 fps=30 max s=1280x720 fps=30
[dshow @ 0]   vcodec=mjpeg  min s=640x360 fps=30 max s=640x360 fps=30
[dshow @ 0]   pixel_format=yuyv422  min s=640x480 fps=30 max s=640x480 fps=30
[dshow @ 0]   pixel_format=yuyv422  min s=1280x720 fps=10 max s=1280x720 fps=10
[dshow @ 0]   pixel_format=yuyv422  min s=320x240 fps=30 max s=320x240 fps=30
'''


class VideoModeTests(unittest.TestCase):
    def test_parse_reads_all_modes(self):
        modes = parse_modes(WEBCAM)
        self.assertEqual(len(modes), 6)
        self.assertIn({'kind': 'pixel_format', 'format': 'yuyv422', 'width': 1280, 'height': 720, 'fps': 10.0}, modes)

    def test_choice_is_640x480_mjpeg_30fps_not_hd_raw(self):
        mode = choose_mode(parse_modes(WEBCAM))
        self.assertEqual((mode['width'], mode['height'], mode['fps'], mode['format']), (640, 480, 30.0, 'mjpeg'))

    def test_falls_back_to_fastest_when_30fps_is_unavailable(self):
        slow = parse_modes('[d]   pixel_format=yuyv422  min s=640x480 fps=15 max s=640x480 fps=15\n[d]   pixel_format=yuyv422  min s=320x240 fps=5 max s=320x240 fps=5\n')
        self.assertEqual(choose_mode(slow)['fps'], 15.0)

    def test_unreadable_modes_mean_device_default(self):
        self.assertIsNone(choose_mode([]))
        self.assertEqual(mode_args(None), [])

    def test_mode_args_for_mjpeg_and_raw(self):
        self.assertEqual(mode_args({'format': 'mjpeg', 'width': 640, 'height': 480, 'fps': 30.0}),
                         ['-video_size', '640x480', '-framerate', '30', '-vcodec', 'mjpeg'])
        self.assertEqual(mode_args({'format': 'yuyv422', 'width': 640, 'height': 480, 'fps': 30.0})[-2:], ['-pixel_format', 'yuyv422'])

    def test_args_put_mode_options_before_the_video_input(self):
        a = build_args('cam', 'mic', {'format': 'mjpeg', 'width': 640, 'height': 480, 'fps': 30.0})
        self.assertLess(a.index('-framerate'), a.index('video=cam'))
        self.assertEqual(a[a.index('-i') + 1], 'video=cam')


class AudioBufferTests(unittest.TestCase):
    def test_audio_input_uses_a_small_buffer_so_video_is_not_batched(self):
        a = build_args('cam', 'mic')
        i = a.index('-audio_buffer_size')
        self.assertEqual(a[i + 1], '50')
        self.assertLess(i, a.index('audio=mic'))            # 옵션은 입력(-i audio=...) 앞에 와야 적용된다
        self.assertLess(a.index('video=cam'), i)             # 영상 입력에는 영향을 주지 않는다


import json
import tempfile
from pathlib import Path
from unittest import mock

from scripts import make_capture_input as mci


class RefreshTests(unittest.TestCase):
    MODE = {'format': 'mjpeg', 'width': 640, 'height': 480, 'fps': 30.0}

    def run_refresh(self, devices, modes, existing=None, **hints):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'in.json'
            if existing is not None:
                out.write_text(json.dumps(existing), encoding='utf-8')
            with mock.patch.object(mci, 'list_devices', return_value=devices), \
                 mock.patch.object(mci, 'list_video_modes', return_value=modes):
                ok = mci.refresh('ffmpeg', out, **hints)
            return ok, json.loads(out.read_text(encoding='utf-8')) if out.exists() else None

    def test_missing_device_returns_false_and_keeps_the_file(self):
        old = mci.build_args('cam', 'mic', self.MODE)
        ok, after = self.run_refresh({'video': [], 'audio': ['mic']}, [self.MODE], existing=old)
        self.assertFalse(ok)
        self.assertEqual(after, old)

    def test_new_device_name_rewrites_the_input(self):
        old = mci.build_args('old cam', 'mic', self.MODE)
        ok, after = self.run_refresh({'video': ['new cam'], 'audio': ['mic']}, [self.MODE], existing=old)
        self.assertTrue(ok)
        self.assertIn('video=new cam', after)

    def test_unreadable_modes_keep_the_known_good_input_for_the_same_devices(self):
        old = mci.build_args('cam', 'mic', self.MODE)
        ok, after = self.run_refresh({'video': ['cam'], 'audio': ['mic']}, [], existing=old)
        self.assertTrue(ok)
        self.assertEqual(after, old)  # still 640x480 30 fps, not the device default

    def test_first_run_without_a_file_writes_one(self):
        ok, after = self.run_refresh({'video': ['cam'], 'audio': ['mic']}, [self.MODE])
        self.assertTrue(ok)
        self.assertEqual(after, mci.build_args('cam', 'mic', self.MODE))

    def test_hint_for_an_absent_device_is_treated_as_missing(self):
        ok, _ = self.run_refresh({'video': ['cam'], 'audio': ['mic']}, [self.MODE], audio='G435')
        self.assertFalse(ok)
