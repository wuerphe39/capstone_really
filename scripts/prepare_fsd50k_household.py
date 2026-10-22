r"""Select FSD50K *eval* clips for a household-noise evaluation of the bark detector (no model scores involved).

Positives: every CC0/CC-BY clip labelled `Bark`. Negatives: speech, doorbell, knock, telephone/ringtone, music, laughter,
crying, cat, alarm, bell, door and other (non-dog) animal clips, taken in deterministic hash order up to a fixed cap per
group. Clips labelled Dog or Bark never become negatives. Clips already used by earlier evaluations (ids recorded in
docs/evidence) and ESC-50 source ids are excluded. FSD50K eval uses the official exhaustive annotation.

Reuses the bounded-range ZIP reader of prepare_fsd50k_subset (no 25 GB download); clips stay in artifacts/ (git-ignored).

    .\.venv\Scripts\python.exe -m scripts.prepare_fsd50k_household
"""
import csv
import glob
import hashlib
import json
import time
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
import soundfile as sf

from scripts.prepare_fsd50k_subset import ROOT, SplitZip, prepare_metadata

OUT = ROOT / 'household_eval'
# group -> (labels that put a clip in the group, cap). First matching group in this order wins.
GROUPS = [
    ('doorbell', {'Doorbell'}, 60), ('knock', {'Knock'}, 60), ('telephone', {'Telephone'}, 60), ('ringtone', {'Ringtone'}, 40),
    ('crying', {'Crying_and_sobbing', 'Baby_cry_and_infant_cry'}, 40), ('laughter', {'Laughter'}, 40),
    ('speech', {'Speech'}, 80), ('cat', {'Cat'}, 60), ('alarm', {'Alarm'}, 40), ('bell', {'Bell'}, 40), ('door', {'Door'}, 40),
    ('music', {'Music'}, 60), ('other_animal', {'Animal'}, 60),
]
FORBIDDEN_NEGATIVE = {'Dog', 'Bark'}


def previously_used_ids():
    ids = set()

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in ('source_id', 'fname') and isinstance(v, (str, int)):
                    ids.add(str(v))
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    for path in glob.glob('docs/evidence/*.json'):
        try:
            walk(json.loads(Path(path).read_text(encoding='utf-8')))
        except ValueError:
            pass
    return ids


def main():
    deadline = time.monotonic() + 90 * 60
    record = prepare_metadata(deadline)
    meta = json.loads((ROOT / 'FSD50K.metadata/eval_clips_info_FSD50K.json').read_text(encoding='utf-8'))
    rows = list(csv.DictReader((ROOT / 'FSD50K.ground_truth/eval.csv').open(encoding='utf-8')))
    esc = json.loads(Path('artifacts/datasets/esc50/manifest.json').read_text())
    excluded = {str(r['src_file']) for r in esc['records'] + esc['excluded']} | previously_used_ids()
    rows = [r for r in rows if r['fname'] not in excluded and any(x in meta[r['fname']]['license'] for x in ('/by/', '/zero/'))]
    order = lambda r: hashlib.sha256(('petmind-household-v1:' + r['fname']).encode()).hexdigest()

    labels = lambda r: set(r['labels'].split(','))
    selected = [('bark', 'positive', r) for r in sorted((r for r in rows if 'Bark' in labels(r)), key=order)]
    taken = {r['fname'] for _, _, r in selected}
    for group, wanted, cap in GROUPS:
        pool = [r for r in sorted(rows, key=order) if r['fname'] not in taken and labels(r) & wanted and not labels(r) & FORBIDDEN_NEGATIVE]
        for r in pool[:cap]:
            selected.append((group, 'negative', r)); taken.add(r['fname'])

    files = [f for f in record['files'] if f['key'].startswith('FSD50K.eval_audio.')]
    files.sort(key=lambda f: (f['key'].endswith('.zip'), f['key']))
    archive = SplitZip(files, deadline)
    OUT.mkdir(exist_ok=True)

    def acquire(item):
        group, kind, row = item
        name = row['fname'] + '.wav'
        entry = archive.entries.get(f'FSD50K.eval_audio/{name}')
        if entry is None or entry['size'] > 12 * 1024 * 1024:
            return None
        path = OUT / name
        if not path.exists():
            for attempt in range(6):   # Zenodo sometimes answers a range request without honouring it: retry, then skip the clip
                try:
                    content = archive.extract(f'FSD50K.eval_audio/{name}')
                    break
                except (ValueError, OSError, requests.RequestException):
                    time.sleep(2 + 3 * attempt)
            else:
                print('skipped (server kept refusing):', name, flush=True)
                return None
            temporary = path.with_suffix('.partial'); temporary.write_bytes(content); temporary.replace(path)
        content = path.read_bytes()
        if zlib.crc32(content) & 0xffffffff != entry['crc']:
            raise ValueError('cached CRC mismatch')
        info = sf.info(path)
        m = meta[row['fname']]
        return {'filename': name, 'source_id': row['fname'], 'group': group, 'expected': int(kind == 'positive'),
                'labels': row['labels'].split(','), 'duration_s': round(info.duration, 3), 'sha256': hashlib.sha256(content).hexdigest(),
                'license': m['license'], 'uploader': m['uploader'], 'title': m['title']}

    records = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for i, rec in enumerate(pool.map(acquire, selected), 1):
            if rec:
                records.append(rec)
            if i % 50 == 0:
                print(f'{i}/{len(selected)}', flush=True)
    manifest = {'source': 'https://zenodo.org/records/4060432 (FSD50K eval, official exhaustive annotation)', 'records': records,
                'selection': 'Bark positives: all CC0/CC-BY; negatives per group in deterministic hash order up to a cap; no Dog/Bark labels; '
                             'earlier-evaluated ids and ESC-50 source ids excluded; no model score used',
                'groups': {g: {'cap': c, 'labels': sorted(w)} for g, w, c in GROUPS},
                'scope': 'selected subset, not natural household prevalence', 'archive_integrity': 'per-entry ZIP CRC32 and local SHA256'}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    from collections import Counter
    print('complete:', len(records), dict(Counter(r['group'] for r in records)))


if __name__ == '__main__':
    main()
