"""WAV ingestion and candidate-event evaluation; not a trained bark classifier."""
from dataclasses import asdict
from math import gcd

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from .bark import BarkDetector
from .context import MotionSummary, PetContext


def analyze_wav(path, max_duration_s=None):
    samples, rate = sf.read(path, dtype='float32', always_2d=True)
    if max_duration_s is not None:
        if not np.isfinite(max_duration_s) or max_duration_s <= 0:
            raise ValueError('max_duration_s must be positive and finite')
        samples = samples[:int(rate * max_duration_s)]
    if rate <= 0 or len(samples) == 0 or len(samples) / rate > 120:
        raise ValueError('audio must be nonempty and no longer than 120 seconds')
    if not np.isfinite(samples).all() or np.abs(samples).max() > 1:
        raise ValueError('audio samples must be finite and within [-1, 1]')
    mono = samples.mean(axis=1)
    factor = gcd(rate, 16000)
    if rate != 16000:
        mono = resample_poly(mono, 16000 // factor, rate // factor).astype(np.float32)
    duration = len(mono) / 16000
    detector = BarkDetector()
    detector.feed(mono)
    detector.finish()
    context = PetContext(timestamp=duration, window_s=duration,
                         bark=detector.summarize(duration, end_s=duration),
                         motion=MotionSummary(duration, 'unknown', {'unknown': duration}))
    return {'context': context.to_dict(), 'sample_rate': 16000, 'original_sample_rate': rate,
            'original_channels': samples.shape[1], 'duration_s': duration,
            'events': [asdict(event) for event in detector.events],
            'envelope': [{'t': i / 16000, 'rms': float(np.sqrt(np.mean(mono[i:i+1600] ** 2)))}
                         for i in range(0, len(mono), max(1600, len(mono)//600))],
            'classifier': 'energy_candidates', 'accuracy_scope': 'candidate detection, not bark identification'}
