"""Prepare four pinned ESC-50 examples for an isolated presentation demo.

The files stay under artifacts/ and are never committed. This does not create
new training data or change the model evaluation splits.
"""
import argparse
import csv
import hashlib
import io
import json
import re
from pathlib import Path

import soundfile as sf

from scripts.prepare_esc50 import BASE, REVISION, download


SAMPLES = {
    '5-203128-A-0.wav': ('dog', 5, '435e476d5d429aa1cc51c23c9b5e5f8f472faf022846996ade18a457621d0552'),
    '5-208030-A-0.wav': ('dog', 5, '8b3f5052dad5383ea171aa8feaead47879bf7b5ae3acaf5a26c5167838a49494'),
    '5-181766-A-10.wav': ('rain', 5, '608fcc0bef32512e2a984c7d3d2cac8ea161f6337ec0056850a6d34f07f8db35'),
    '1-100032-A-0.wav': ('dog', 1, 'f40a849a2375c8c63312a73dd2dd6c74007301fcc21b4be2ece29a642831e3d8'),
}


def validated_audio(content, expected_hash):
    if hashlib.sha256(content).hexdigest() != expected_hash:
        raise ValueError('ESC-50 source hash changed; do not reuse this sample')
    info = sf.info(io.BytesIO(content))
    if info.format != 'WAV' or info.samplerate != 44100 or abs(info.duration - 5) > .001:
        raise ValueError('unexpected ESC-50 audio format or duration')
    return content


def original_attribution(license_text, filename):
    original = Path(filename).stem.rsplit('-', 1)[0]+'.ogg'
    prefix = f'- [{original}]: '
    line = next((line for line in license_text.decode('utf-8').splitlines()
                 if line.startswith(prefix)), None)
    match = re.fullmatch(r'- \[[^]]+\]: clip derived from (.+) \((https?://[^)]+)\) by (.+) \[([^]]+)\]',
                         line or '')
    if match is None:
        raise ValueError(f'{filename}: original source attribution missing from ESC-50 license')
    title, url, author, original_license = match.groups()
    return {'original_title': title, 'original_source_url': url,
            'original_author': author, 'original_license': original_license}


def prepare(output, source_dir=None):
    output = Path(output)
    source_dir = Path(source_dir) if source_dir else None
    metadata = (source_dir.parent/'esc50.csv').read_bytes() if source_dir else download(BASE+'/meta/esc50.csv')
    license_text = (source_dir.parent/'LICENSE').read_bytes() if source_dir else download(BASE+'/LICENSE')
    rows = {row['filename']: row for row in csv.DictReader(io.StringIO(metadata.decode('utf-8')))}
    selected = []
    for name, (category, fold, digest) in SAMPLES.items():
        row = rows[name]
        if row['category'] != category or row['fold'] != str(fold) or row['esc10'] != 'True':
            raise ValueError(f'{name}: official metadata does not match the pinned test example')
        cached = output/'audio'/name
        if cached.exists():
            content = cached.read_bytes()
        elif source_dir:
            content = (source_dir/name).read_bytes()
        else:
            content = download(BASE+'/audio/'+name)
        validated_audio(content, digest)
        selected.append((name, content, row, digest, original_attribution(license_text, name)))
    (output/'audio').mkdir(parents=True, exist_ok=True)
    for name, content, _, _, _ in selected:
        target = output/'audio'/name
        temporary = target.with_suffix('.partial')
        temporary.write_bytes(content)
        temporary.replace(target)
    (output/'esc50.csv').write_bytes(metadata)
    (output/'LICENSE').write_bytes(license_text)
    manifest = {'source': 'https://github.com/karolpiczak/ESC-50', 'revision': REVISION,
                'purpose': 'public-audio UI demo only; official folds 1 and 5, never training or threshold selection',
                'records': [{'filename': name, 'category': row['category'], 'fold': int(row['fold']),
                             'src_file': row['src_file'], 'license': 'CC BY', 'sha256': digest,
                             **attribution}
                            for name, _, row, digest, attribution in selected]}
    (output/'demo_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('artifacts/datasets/esc50_demo'))
    parser.add_argument('--source-dir', type=Path, help='reuse an already downloaded official ESC-50 audio directory')
    args = parser.parse_args()
    result = prepare(args.output, args.source_dir)
    print(f"validated {len(result['records'])} ESC-50 test examples in {args.output}")


if __name__ == '__main__':
    main()
