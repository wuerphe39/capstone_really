"""Build one labeled presentation clip: doorbell, door knock, then public dog bark.

The ordered source mix is a simulated scene, not evidence of an actual visitor.
Original audio and output remain in Git-ignored artifacts.
"""
import hashlib
import json
import subprocess
from pathlib import Path

import imageio_ffmpeg
import numpy as np
import requests
import soundfile as sf

from pet_monitor.audio_lstm import AudioPredictor


ROOT = Path('artifacts/ai_sound_demo_20261012/visitor')
FSD = Path('artifacts/datasets/fsd50k/eval_subset')
RATE = 16000
SOURCES = {
    'doorbell': {
        'url': 'https://commons.wikimedia.org/wiki/Special:Redirect/file/Sound_Effect_-_Door_Bell.ogg',
        'page': 'https://commons.wikimedia.org/wiki/File:Sound_Effect_-_Door_Bell.ogg',
        'author': 'Amada44', 'license': 'CC0 1.0', 'filename': 'doorbell.ogg',
    },
    'knock': {
        'url': 'https://commons.wikimedia.org/wiki/Special:Redirect/file/Door_knocker_audio.ogg',
        'page': 'https://commons.wikimedia.org/wiki/File:Door_knocker_audio.ogg',
        'author': 'Mx. Granger', 'license': 'CC0 1.0', 'filename': 'door_knock.ogg',
    },
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def download(source):
    path = ROOT / source['filename']
    if not path.exists():
        response = requests.get(source['url'], timeout=30,
                                headers={'User-Agent': 'PetMindCapstoneDemo/1.0 (educational project)'})
        response.raise_for_status()
        if not response.content.startswith(b'OggS'):
            raise ValueError(f"Unexpected audio response for {source['filename']}")
        path.write_bytes(response.content)
    return path


def decode(path):
    command = [imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-i', str(path),
               '-ac', '1', '-ar', str(RATE), '-f', 'f32le', 'pipe:1']
    return np.frombuffer(subprocess.check_output(command), dtype='<f4').copy()


def scaled(values, peak):
    if not len(values) or np.max(np.abs(values)) < 1e-6:
        raise ValueError('Source audio is silent')
    return values * (peak / np.max(np.abs(values)))


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    originals = {name: download(source) for name, source in SOURCES.items()}
    fsd_manifest = json.loads((FSD / 'manifest.json').read_text(encoding='utf-8'))['records']
    bark_info = next(row for row in fsd_manifest if row['source_id'] == '15791')
    bark_path = FSD / bark_info['filename']
    if sha256(bark_path) != bark_info['sha256'] or 'Bark' not in bark_info['labels']:
        raise ValueError('FSD50K bark source integrity or label mismatch')

    # Fixed source order and timing; do not move events to tune a classifier score.
    output = np.zeros(RATE * 10, dtype=np.float32)
    parts = [
        ('doorbell', originals['doorbell'], 0.2, 2.4, 0.55),
        ('knock', originals['knock'], 2.8, 1.5, 0.60),
        ('bark', bark_path, 5.0, 5.0, 0.70),
    ]
    intervals = []
    for name, path, start, duration, peak in parts:
        sample = scaled(decode(path)[:round(duration * RATE)], peak)
        left = round(start * RATE)
        output[left:left + len(sample)] += sample
        intervals.append({'sound': name, 'start_s': start,
                          'end_s': round(start + len(sample) / RATE, 3)})
    destination = ROOT / 'doorbell_knock_then_bark.wav'
    sf.write(destination, np.clip(output, -0.99, 0.99), RATE, subtype='PCM_16')
    predictor = AudioPredictor('artifacts/audio_lstm/household_bark_candidate.pt')
    result = predictor.predict(destination)
    manifest = {
        'purpose': 'Simulated visitor-like sequence; no visitor or bark cause is observed.',
        'output': destination.name, 'output_sha256': sha256(destination),
        'sample_rate': RATE, 'duration_s': 10.0, 'intervals': intervals,
        'sources': {name: {**source, 'sha256': sha256(originals[name])}
                    for name, source in SOURCES.items()} | {
            'bark': {'page': 'https://zenodo.org/records/4060432',
                     'dataset': 'FSD50K', 'source_id': '15791',
                     'author': bark_info['uploader'], 'license': bark_info['license'],
                     'sha256': bark_info['sha256']}},
        'experimental_lstm': result,
        'evaluation_scope': 'One constructed demonstration, not independent accuracy evaluation.',
    }
    (ROOT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                        encoding='utf-8')
    print(json.dumps({'file': str(destination), 'sha256': manifest['output_sha256'],
                      'windows': result['windows']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
