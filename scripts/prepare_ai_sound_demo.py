"""Prepare transparently labeled TTS + public bark demo clips for the web UI.

These are simulated presentation inputs, never training/evaluation ground truth.
"""
import argparse
import hashlib
import json
from math import gcd
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from pet_monitor.audio_lstm import AudioPredictor

ROOT = Path('artifacts/ai_sound_demo_20261012')
FSD = Path('artifacts/datasets/fsd50k/eval_subset')
RATE = 16000


def wave(path):
    data, rate = sf.read(path, dtype='float32', always_2d=True)
    mono = data.mean(axis=1)
    if rate != RATE:
        d = gcd(rate, RATE)
        mono = resample_poly(mono, RATE//d, rate//d).astype('float32')
    return np.pad(mono[:RATE*5], (0,max(0,RATE*5-len(mono))))


def save(path, audio):
    sf.write(path,np.clip(audio,-.99,.99),RATE,subtype='PCM_16')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--voice', choices=('windows', 'gemini38'), default='windows')
    args = parser.parse_args()
    output = ROOT / 'natural' if args.voice == 'gemini38' else ROOT
    output.mkdir(parents=True, exist_ok=True)
    manifest=json.loads((FSD/'manifest.json').read_text(encoding='utf-8'))['records']
    bark=next(r for r in manifest if r['source_id']=='15791')
    assert hashlib.sha256((FSD/bark['filename']).read_bytes()).hexdigest()==bark['sha256']
    assert 'Bark' in bark['labels']
    tts=ROOT/('home_speech_gemini38.wav' if args.voice == 'gemini38' else 'home_speech_tts.wav')
    if not tts.is_file():
        raise FileNotFoundError(f'Generate {tts.name} first')
    bark_audio=wave(FSD/bark['filename'])
    speech_audio=wave(tts)
    rms=lambda a:float(np.sqrt(np.mean(a*a)+1e-12))
    predictor=AudioPredictor('artifacts/audio_lstm/esc50_lstm.pt')
    candidate=AudioPredictor('artifacts/audio_lstm/household_bark_candidate.pt') if args.voice == 'gemini38' else None
    cases=[]
    gains = (.05,.1,.2,.4,.8) if args.voice == 'gemini38' else (.1,.2,.4)
    for label, audio in [('tts_only',speech_audio)]+[(f'bark_tts_{gain}',bark_audio+speech_audio*(gain*rms(bark_audio)/rms(speech_audio))) for gain in gains]:
        path=output/(label+'.wav')
        digest=save(path,audio)
        result=predictor.predict(path)
        cases.append({'filename':path.name,'sha256':digest,'score':result['dog_score'],
                      'threshold':result['threshold'],'detected':result['dog_score']>=result['threshold'],
                      'candidate_score':candidate.predict(path)['dog_score'] if candidate else None,
                      'case':label})
    report={'kind':f'AI-generated {args.voice} speech + real FSD50K public bark; simulated demo only',
            'tts_text':'문 닫고 갈게. 잠깐만 기다려. 금방 돌아올게.',
            'tts_sha256':hashlib.sha256(tts.read_bytes()).hexdigest(),
            'bark_source_id':bark['source_id'],'bark_sha256':bark['sha256'],
            'bark_uploader':bark['uploader'],'bark_license':bark['license'],
            'source':'https://zenodo.org/records/4060432',
            'mix':'first five seconds; speech RMS relative to bark RMS as filename; peak clipped to 0.99',
            'scope':'previously inspected eval source; no independence, accuracy, or household claim',
            'cases':cases}
    (output/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(cases,ensure_ascii=False))


if __name__=='__main__':main()
