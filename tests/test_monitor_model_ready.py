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
