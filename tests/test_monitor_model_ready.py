import unittest

from scripts.monitor_audio_events import model_ready


class ModelReadyTests(unittest.TestCase):
    def test_yamnet_result_counts_as_ready(self):
        self.assertTrue(model_ready({'audio_model': {'dog_score': 0.8, 'threshold': 0.05}}))

    def test_lstm_result_counts_as_ready(self):
        self.assertTrue(model_ready({'audio_lstm': {'dog_score': 0.8}}))

    def test_no_model_output_is_not_ready(self):
        self.assertFalse(model_ready({'model_status': 'yamnet_model_failed'}))
        self.assertFalse(model_ready({}))


if __name__ == '__main__':
    unittest.main()


class RunFfmpegRetryTests(unittest.TestCase):
    def test_transient_failure_is_retried_once(self):
        import subprocess
        from unittest import mock
        from scripts import monitor_audio_events as m
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            if len(calls) == 1:
                raise subprocess.CalledProcessError(1, cmd)

        with mock.patch.object(m.subprocess, 'run', fake_run), mock.patch.object(m.time, 'sleep', lambda s: None):
            m.run_ffmpeg('ffmpeg', ['-i', 'x'])
        self.assertEqual(len(calls), 2)

    def test_persistent_failure_still_raises(self):
        import subprocess
        from unittest import mock
        from scripts import monitor_audio_events as m

        def always_fail(cmd, **kw):
            raise subprocess.CalledProcessError(1, cmd)

        with mock.patch.object(m.subprocess, 'run', always_fail), mock.patch.object(m.time, 'sleep', lambda s: None):
            with self.assertRaises(subprocess.CalledProcessError):
                m.run_ffmpeg('ffmpeg', ['-i', 'x'])


class CaptureCommandPreviewTests(unittest.TestCase):
    def test_preview_is_a_second_output_on_stdout_only_when_requested(self):
        from pathlib import Path
        from scripts.monitor_audio_events import PREVIEW_FPS, build_capture_command
        base = build_capture_command('ffmpeg', ['-i', 'in'], '0:v:0', '1:a:0', Path('f'))
        self.assertNotIn('image2pipe', base)
        with_preview = build_capture_command('ffmpeg', ['-i', 'in'], '0:v:0', '1:a:0', Path('f'), True)
        self.assertEqual(with_preview[:len(base)], base)       # segment output is unchanged
        self.assertEqual(with_preview[-1], 'pipe:1')
        self.assertIn('image2pipe', with_preview)
        self.assertIn(f'fps={PREVIEW_FPS},scale=640:-2', with_preview)
        self.assertEqual(with_preview.count('-map'), 3)         # video + audio for segments, video for preview
