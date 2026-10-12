"""Create clearly labeled simulated home-noise cases from verified public FSD50K sources."""
import hashlib
import json
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from scipy.signal import resample_poly

from pet_monitor.audio_lstm import AudioPredictor

SOURCE = Path('artifacts/datasets/fsd50k/eval_subset')
TARGET = Path('artifacts/household_bark_20261012')
RATE = 16000
SECONDS = 5


def read_audio(row):
    path = SOURCE / row['filename']
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == row['sha256']
    data, rate = sf.read(path, dtype='float32', always_2d=True)
    mono = data.mean(axis=1)
    if rate != RATE:
        from math import gcd
        n = gcd(rate, RATE)
        mono = resample_poly(mono, RATE//n, rate//n)
    return np.pad(mono[:RATE*SECONDS], (0,max(0,RATE*SECONDS-len(mono)))).astype('float32')


def main():
    torch.set_num_threads(2)
    records = json.loads((SOURCE/'manifest.json').read_text(encoding='utf-8'))['records']
    by_id = {r['source_id']:r for r in records}
    bark_id = '15791'
    bark = read_audio(by_id[bark_id])
    predictor = AudioPredictor('artifacts/audio_lstm/esc50_lstm.pt')
    TARGET.mkdir(parents=True,exist_ok=True)
    cases=[]
    for label,noise_id in [('door','195579'),('dishes','38957'),('speech','400092')]:
        noise = read_audio(by_id[noise_id])
        # Background at 40% of barking RMS. Fixed before model inference.
        rms = lambda a: float(np.sqrt(np.mean(a*a)+1e-12))
        scaled = noise * (.4*rms(bark)/rms(noise))
        mix = bark+scaled
        peak = float(np.max(np.abs(mix)))
        if peak > .99: mix = mix*(.99/peak)
        path = TARGET/f'bark_with_{label}.wav'
        sf.write(path,mix,RATE,subtype='PCM_16')
        prediction = predictor.predict(path)
        cases.append({'filename':path.name,'bark_source_id':bark_id,'noise_source_id':noise_id,
                      'noise_label':label,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                      'score':prediction['dog_score'],'threshold':prediction['threshold'],
                      'detected':prediction['dog_score']>=prediction['threshold'],
                      'windows':prediction['windows'],
                      'bark_license':by_id[bark_id]['license'],'noise_license':by_id[noise_id]['license'],
                      'bark_uploader':by_id[bark_id]['uploader'],'noise_uploader':by_id[noise_id]['uploader']})
    report={'type':'simulated mixtures of real FSD50K public audio; NOT real household recordings',
            'source':'https://zenodo.org/records/4060432',
            'split':'FSD50K eval; already inspected, exploratory demonstration only',
            'mix':'first 5 seconds of bark source + household source at 0.4 x bark RMS; peak-limited if required',
            'cases':cases}
    (TARGET/'mixture_results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps([{'case':c['filename'],'score':round(c['score'],3),
                       'detected':c['detected']} for c in cases]))


if __name__=='__main__':main()
