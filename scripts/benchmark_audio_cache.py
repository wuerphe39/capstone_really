"""Compare per-upload model load+inference with bounded content-keyed cache."""
import hashlib
import json
import statistics
import time
from pathlib import Path
import torch
from pet_monitor.audio_lstm import AudioPredictor
from pet_monitor.audio_model_cache import get_audio_predictor


def main():
    torch.set_num_threads(2)
    checkpoint = Path('artifacts/audio_lstm/esc50_lstm.pt')
    audio = Path('artifacts/media/1-100032-A-0.wav')
    results, predictions = {}, {}
    for name, loader in [('before', AudioPredictor), ('after', get_audio_predictor)]:
        loader(checkpoint).predict(audio)  # Same warm-up protocol.
        times = []
        for _ in range(10):
            start = time.perf_counter()
            prediction = loader(checkpoint).predict(audio)
            times.append(time.perf_counter()-start)
        predictions[name] = prediction
        results[name] = {'seconds': times, 'median_seconds': statistics.median(times)}
    equal = predictions['before'] == predictions['after']
    report = {'results': results, 'identical_predictions': equal,
              'checkpoint_sha256': hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
              'audio_sha256': hashlib.sha256(audio.read_bytes()).hexdigest(),
              'scope': 'one public 5s clip, CPU 2 threads, ten repeated model-load+inference calls; not full API latency'}
    Path('docs/evidence/audio_cache_benchmark.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))
    assert equal


if __name__ == '__main__': main()
