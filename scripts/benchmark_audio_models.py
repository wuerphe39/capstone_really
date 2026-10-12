"""Local CPU audio inference cost, no feature cache and no network download."""
import hashlib
import json
import platform
import time
from math import gcd
from pathlib import Path

import numpy as np
import psutil
import soundfile as sf
import torch
from scipy.signal import resample_poly

from pet_monitor.audio_lstm import AudioPredictor
from scripts.evaluate_clap_audio import MODEL_DIR, REVISION


def main():
    torch.set_num_threads(2)
    torch.manual_seed(20261011)
    root = Path('artifacts/datasets/esc50')
    manifest = json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    # Predeclared categories; measurement never selects files by model scores.
    rows = [next(r for r in manifest['records'] if r['split'] == 'test' and r['category'] == c)
            for c in ('dog', 'rain', 'clock_tick')]
    process = psutil.Process()
    report = {'platform': platform.platform(), 'processor': platform.processor(),
              'torch': torch.__version__, 'threads': 2, 'device': 'cpu', 'models': {},
              'limitations': ['three five-second clips, three repetitions each; not load testing',
                              'RSS snapshots are not peak allocation; OS file cache not cleared',
                              'model load excludes library import; CLAP excludes text encoding and retrieval',
                              'same process loads LSTM then CLAP; memory is not an isolated incremental measurement',
                              'not measured on Raspberry Pi; not evidence of live recording support']}
    for name in ('lstm', 'clap'):
        if name == 'clap':
            from transformers import ClapModel, ClapProcessor
        start = time.perf_counter()
        if name == 'lstm':
            path = Path('artifacts/audio_lstm/esc50_lstm.pt')
            model = AudioPredictor(path)
            infer = lambda p: model.predict(p)
        else:
            path = MODEL_DIR/'pytorch_model.bin'
            processor = ClapProcessor.from_pretrained(MODEL_DIR, local_files_only=True)
            model = ClapModel.from_pretrained(MODEL_DIR, local_files_only=True, weights_only=True).eval()
            def infer(p):
                values, rate = sf.read(p, dtype='float32', always_2d=True)
                divisor = gcd(rate, 48000)
                samples = resample_poly(values.mean(1), 48000//divisor, rate//divisor).astype(np.float32)
                with torch.inference_mode():
                    return model.get_audio_features(**processor(audio=[samples], sampling_rate=48000, return_tensors='pt'))
        load_s = time.perf_counter()-start
        timings = []
        for row in rows:
            audio = root/'audio'/row['filename']
            if hashlib.sha256(audio.read_bytes()).hexdigest() != row['sha256']:
                raise ValueError('audio checksum mismatch')
            start = time.perf_counter(); infer(audio); first_s = time.perf_counter()-start
            runs = []
            for _ in range(3):
                start = time.perf_counter(); infer(audio); runs.append(time.perf_counter()-start)
            timings.append({'filename': row['filename'], 'sha256': row['sha256'], 'duration_s': 5,
                            'first_call_s': first_s, 'repeat_s': runs,
                            'median_realtime_factor': float(np.median(runs)/5)})
        values = {'load_s': load_s, 'checkpoint_bytes': path.stat().st_size,
                  'checkpoint_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                  'rss_after_runs_bytes': process.memory_info().rss, 'timings': timings}
        if name == 'clap': values['revision'] = REVISION
        report['models'][name] = values
        print(json.dumps({'model': name, 'load_s': load_s,
                          'median_inference_s': float(np.median([t for r in timings for t in r['repeat_s']])),
                          'rss_bytes': values['rss_after_runs_bytes']}), flush=True)
    Path('docs/evidence/audio_runtime_benchmark.json').write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
