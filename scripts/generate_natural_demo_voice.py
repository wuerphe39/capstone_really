"""Generate a local-only Korean presentation voice with Gemini TTS.

This is a synthetic sound fixture, never a real household recording or label.
The RAG model remains configured independently by PETMIND_GEMINI_MODEL.
"""
import base64
import hashlib
import json
import wave
from pathlib import Path

import requests

from petmind.backend.settings import settings


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'artifacts' / 'ai_sound_demo_20261012'
MODEL = 'gemini-3.8-flash-tts'
SCRIPT = '문 닫고 갈게. 잠깐만 기다려. 금방 돌아올게.'


def main():
    if not settings.gemini_api_key:
        raise RuntimeError('Set GEMINI_API_KEY in the local .env; never pass it on the command line.')
    payload = {
        'model': MODEL,
        'input': [{'type': 'user_input', 'content': [{'type': 'text', 'text': SCRIPT,
            'annotations': [{'type': 'speech_metadata',
                             'style': 'Natural Korean conversation at home, warm and unhurried, with realistic pauses.'}]}]}],
        'response_format': {'type': 'audio'},
        'generation_config': {'speech_config': [{'voice': 'Kore'}]},
    }
    response = requests.post('https://generativelanguage.googleapis.com/v1beta/interactions',
                             headers={'x-goog-api-key': settings.gemini_api_key, 'Content-Type': 'application/json'},
                             json=payload, timeout=120)
    if not response.ok:
        raise RuntimeError(f'Gemini TTS HTTP {response.status_code}; no audio saved')
    data = response.json()
    blocks = [content for step in data.get('steps', []) if step.get('type') == 'model_output'
              for content in step.get('content', []) if content.get('type') == 'audio']
    if not blocks:
        raise RuntimeError('Gemini TTS returned no audio block')
    audio = base64.b64decode(blocks[-1]['data'], validate=True)
    if not audio.startswith(b'RIFF'):
        raise RuntimeError('Gemini TTS did not return a WAV file')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / 'home_speech_gemini38.wav'
    path.write_bytes(audio)
    with wave.open(str(path)) as wav:
        seconds = wav.getnframes() / wav.getframerate()
        rate = wav.getframerate()
    info = {'model': MODEL, 'voice': 'Kore', 'script': SCRIPT, 'duration_s': seconds,
            'sample_rate': rate, 'sha256': hashlib.sha256(audio).hexdigest(),
            'scope': 'AI-generated presentation sound only; not training/evaluation ground truth'}
    (OUTPUT / 'natural_voice_manifest.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'model': MODEL, 'duration_s': round(seconds, 2), 'sample_rate': rate,
                      'sha256': info['sha256']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
