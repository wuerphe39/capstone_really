"""Build explicitly labeled replay videos from publicly provided DAVIS image sequences."""
import hashlib
import argparse
import json
import zipfile
from pathlib import Path

import cv2
import numpy as np
import requests

URL = 'https://data.vision.ee.ethz.ch/csergi/share/davis/DAVIS-2017-trainval-480p.zip'
FOLDER = Path('artifacts/media')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sequence', choices=['dog', 'dog-gooses', 'dogs-jump', 'dogs-scale'], default='dog')
    args = parser.parse_args()
    sequence = args.sequence
    FOLDER.mkdir(parents=True, exist_ok=True)
    archive = FOLDER / 'DAVIS-2017-trainval-480p.zip'
    if not zipfile.is_zipfile(archive):
        partial = archive.with_suffix('.zip.part')
        with requests.get(URL, stream=True, timeout=(20, 60)) as response:
            response.raise_for_status()
            with partial.open('wb') as stream:
                for chunk in response.iter_content(4*1024*1024):
                    stream.write(chunk)
        if not zipfile.is_zipfile(partial):
            raise ValueError('download is not a valid DAVIS archive')
        partial.replace(archive)
    with zipfile.ZipFile(archive) as dataset:
        names = sorted(n for n in dataset.namelist() if f'/JPEGImages/480p/{sequence}/' in n and n.endswith('.jpg'))
        if not names:
            raise ValueError('dog sequence missing')
        frames = [cv2.imdecode(np.frombuffer(dataset.read(name), np.uint8), cv2.IMREAD_COLOR) for name in names]
        (FOLDER / 'DAVIS_README.md').write_bytes(dataset.read('DAVIS/README.md'))
        (FOLDER / 'DAVIS_SOURCES.md').write_bytes(dataset.read('DAVIS/SOURCES.md'))
    manifest_path = FOLDER / 'manifest.json'
    items = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else []
    items = [item for item in items if not item.get('filename', '').startswith(f'davis_{sequence}_')]
    for fps in [5, 25]:
        filename = f'davis_{sequence}_replay_{fps}fps.mp4'
        path = FOLDER / filename
        height, width = frames[0].shape[:2]
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), fps, (width, height))
        if not writer.isOpened():
            raise ValueError('MP4 encoder unavailable')
        for frame in frames:
            writer.write(frame)
        writer.release()
        items.append({'filename': filename, 'url': URL, 'source_page': 'https://davischallenge.org/davis2017/code.html',
                      'attribution': f'DAVIS contributors; {sequence} sequence; Perazzi et al. 2016 / Pont-Tuset et al. 2017; original source in DAVIS_SOURCES.md',
                      'license': 'DAVIS Terms of Use CC BY-NC 4.0; see DAVIS_README.md and DAVIS_SOURCES.md',
                      'type': 'video', 'frames': len(frames), 'replay_fps': fps, 'original_fps_verified': False,
                      'transformation': f'JPEG sequence reconstructed at {fps}fps for a replay demo; this is not original recording time',
                      'camera_motion': True, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    manifest_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Prepared {len(frames)} dog frames as separate 5fps/25fps replay inputs; original timing unverified')


if __name__ == '__main__':
    main()
