"""Download fixed public input samples with attribution and SHA-256 manifests."""
import csv
import argparse
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import quote

import requests

DEST = Path('artifacts/media')
RAW = 'https://raw.githubusercontent.com/karolpiczak/ESC-50/master/'


def download(url, path):
    if not path.exists():
        response = requests.get(url, timeout=60, headers={'User-Agent': 'PetMind-Capstone/0.1 (academic prototype)'})
        response.raise_for_status()
        path.write_bytes(response.content)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--commons-video', action='store_true', help='Optional source; may be rate-limited')
    args = parser.parse_args()
    DEST.mkdir(parents=True, exist_ok=True)
    metadata = requests.get(RAW + 'meta/esc50.csv', timeout=30)
    metadata.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(metadata.text)))
    license_response = requests.get(RAW + 'LICENSE', timeout=30)
    license_response.raise_for_status()
    (DEST / 'ESC50_LICENSE.txt').write_text(license_response.text, encoding='utf-8')
    items = []
    for category in ['dog', 'rain', 'sea_waves', 'clock_tick']:
        for row in [r for r in rows if r['category'] == category][:5]:
            path = DEST / row['filename']
            url = RAW + 'audio/' + row['filename']
            items.append({'filename': path.name, 'url': url, 'category': category,
                          'source_page': 'https://github.com/karolpiczak/ESC-50',
                          'attribution': 'See ESC50_LICENSE.txt, source ID ' + row['src_file'],
                          'license': 'CC BY (ESC-10 subset)' if row['esc10'] == 'True' else 'CC BY-NC',
                          'sha256': download(url, path), 'duration_s': 5, 'type': 'audio'})
    existing = DEST / 'manifest.json'
    if existing.exists():
        items += [item for item in json.loads(existing.read_text(encoding='utf-8')) if item['type'] == 'video']
    if not args.commons_video:
        existing.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'Prepared {len(items)} public inputs and attribution manifest', flush=True)
        return
    filename = 'Dog_walking_in_the_Mission_in_San_Francisco.ogv'
    digest = hashlib.md5(filename.encode()).hexdigest()
    # Official lower-resolution transcode avoids downloading the larger original.
    url = f'https://upload.wikimedia.org/wikipedia/commons/transcoded/{digest[0]}/{digest[:2]}/{quote(filename)}/{quote(filename)}.360p.vp9.webm'
    (DEST / 'manifest.json').write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')
    items.append({'filename': 'dog_walk_360p.webm', 'url': url,
                  'source_page': 'https://commons.wikimedia.org/wiki/File:' + filename,
                  'attribution': 'Sage Ross, Dog walking in the Mission in San Francisco, 2011',
                  'license': 'CC BY-SA 3.0', 'type': 'video', 'camera_motion': True,
                  'rendition': 'official 360p VP9 transcode',
                  'sha256': download(url, DEST / 'dog_walk_360p.webm')})
    (DEST / 'manifest.json').write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Prepared {len(items)} public inputs and attribution manifest', flush=True)


if __name__ == '__main__':
    main()
