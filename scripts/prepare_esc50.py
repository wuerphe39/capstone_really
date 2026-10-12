"""Fetch the official frozen ESC-50 release; cache validated WAVs and provenance."""
import csv
import hashlib
import io
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
import soundfile as sf

REVISION = '33c8ce9eb2cf0b1c2f8bcf322eb349b6be34dbb6'
BASE = f'https://raw.githubusercontent.com/karolpiczak/ESC-50/{REVISION}'
ROOT = Path('artifacts/datasets/esc50')


def separate_sources(records):
    """Keep test intact; exclude earlier-split copies of a shared source/hash."""
    priority = {'train': 0, 'validation': 1, 'test': 2}
    owners = {}
    for row in records:
        for key in (('source',row['src_file']),('hash',row['sha256'])):
            owners[key] = max(owners.get(key,0), priority[row['split']])
    kept, excluded = [], []
    for row in records:
        if any(owners[key] > priority[row['split']] for key in
               (('source',row['src_file']),('hash',row['sha256']))):
            excluded.append({**row,'reason':'same source or exact audio in later evaluation split'})
        else:
            kept.append(row)
    return kept, excluded


def download(url):
    response = requests.get(url, timeout=90)
    response.raise_for_status()
    return response.content


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT/'audio').mkdir(exist_ok=True)
    metadata = download(BASE+'/meta/esc50.csv')
    (ROOT/'esc50.csv').write_bytes(metadata)
    (ROOT/'LICENSE').write_bytes(download(BASE+'/LICENSE'))
    rows = list(csv.DictReader(io.StringIO(metadata.decode())))
    def fetch(row):
        name = row['filename']
        if Path(name).name != name:
            raise ValueError('invalid source filename')
        path = ROOT/'audio'/name
        if not path.exists():
            content = download(BASE+'/audio/'+name)
            # Decode before committing the cache; interrupted downloads are not reused.
            signal, rate = sf.read(io.BytesIO(content))
            if rate != 44100 or len(signal) != 220500:
                raise ValueError('unexpected ESC duration/sample rate')
            temporary = path.with_suffix('.partial')
            temporary.write_bytes(content)
            temporary.replace(path)
        content = path.read_bytes()
        signal, rate = sf.read(io.BytesIO(content))
        if rate != 44100 or len(signal) != 220500:
            raise ValueError('invalid cached audio')
        return {**row, 'sha256': hashlib.sha256(content).hexdigest(),
                'license': 'CC BY' if row['esc10'] == 'True' else 'CC BY-NC',
                'split': 'train' if int(row['fold']) <= 3 else 'validation' if row['fold'] == '4' else 'test'}
    records = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for i, result in enumerate(pool.map(fetch, rows), 1):
            records.append(result)
            if i % 100 == 0:
                print(f'validated {i}/{len(rows)}', flush=True)
    # Official metadata has several source IDs shared by different classes/folds.
    records, excluded = separate_sources(records)
    groups = {}
    for record in records:
        groups.setdefault(record['src_file'], set()).add(record['split'])
    if any(len(splits) != 1 for splits in groups.values()):
        raise ValueError('source leakage across splits')
    manifest = {'source': 'https://github.com/karolpiczak/ESC-50', 'revision': REVISION,
                'target': 'Dog vs other ESC classes; not emotion or individual dog identity',
                'policy': 'official folds 1-3 train, 4 validation, 5 frozen test; earlier-split shared-source/hash copies excluded',
                'records': records, 'excluded': excluded}
    (ROOT/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('complete: 2000 validated files', flush=True)


if __name__ == '__main__':
    main()
