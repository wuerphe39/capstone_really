"""Select official FSD50K clips without downloading 25 GB of split ZIP archives.

Uses bounded HTTP ranges, ZIP CRC verification and source-ID exclusion.
No model scores influence sample selection. Each clip retains its own license.
"""
import argparse
import csv
import hashlib
import json
import struct
import time
import zlib
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
import soundfile as sf

ROOT = Path('artifacts/datasets/fsd50k')


def remaining_timeout(deadline, maximum=90):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('FSD preparation exceeded its time budget')
    return min(maximum, max(1, remaining))


def prepare_metadata(deadline):
    ROOT.mkdir(parents=True,exist_ok=True)
    record_path = ROOT/'record.json'
    if not record_path.exists():
        response = requests.get('https://zenodo.org/api/records/4060432',timeout=remaining_timeout(deadline,60))
        response.raise_for_status(); record_path.write_text(json.dumps(response.json()),encoding='utf-8')
    record = json.loads(record_path.read_text(encoding='utf-8'))
    for item in record['files']:
        if item['key'] not in {'FSD50K.ground_truth.zip','FSD50K.metadata.zip','FSD50K.doc.zip'}: continue
        path = ROOT/item['key']
        if not path.exists():
            response = requests.get(item['links']['self'],timeout=remaining_timeout(deadline)); response.raise_for_status()
            path.write_bytes(response.content)
        algorithm,digest = item['checksum'].split(':')
        if hashlib.new(algorithm,path.read_bytes()).hexdigest() != digest:
            raise ValueError('official metadata checksum mismatch')
        with zipfile.ZipFile(path) as archive:
            if any(not (ROOT/name).resolve().is_relative_to(ROOT.resolve()) for name in archive.namelist()):
                raise ValueError('unsafe metadata path')
            archive.extractall(ROOT)
    return record


class SplitZip:
    def __init__(self, files, deadline):
        self.files = files
        self.deadline = deadline
        self.starts = [0]
        for item in files: self.starts.append(self.starts[-1]+item['size'])
        last = files[-1]
        tail = self.read(self.starts[-2]+max(0,last['size']-65557), min(last['size'],65557))
        index = tail.rfind(b'PK\x05\x06')
        if index < 0: raise ValueError('ZIP directory missing')
        end = struct.unpack('<4s4H2IH',tail[index:index+22])
        if end[4] == 65535 or end[5] == 0xffffffff: raise ValueError('ZIP64 not supported')
        directory = self.read(self.starts[end[2]]+end[6],end[5])
        self.entries = {}
        offset = 0
        for _ in range(end[4]):
            fields = struct.unpack('<4s6H3I5H2I',directory[offset:offset+46])
            if fields[0] != b'PK\x01\x02': raise ValueError('invalid central directory')
            name = directory[offset+46:offset+46+fields[10]].decode('utf-8')
            self.entries[name] = {'flags':fields[3],'method':fields[4],'crc':fields[7],
                'compressed':fields[8],'size':fields[9], 'offset':self.starts[fields[13]]+fields[16]}
            offset += 46+fields[10]+fields[11]+fields[12]

    def read(self, offset, count):
        if count < 0 or count > 32*1024*1024 or offset < 0 or offset+count > self.starts[-1]:
            raise ValueError('invalid archive range')
        chunks = []
        while count:
            disk = next(i for i in range(len(self.files)) if self.starts[i] <= offset < self.starts[i+1])
            local = offset-self.starts[disk]
            length = min(count,self.files[disk]['size']-local)
            expected = f'bytes {local}-{local+length-1}/{self.files[disk]["size"]}'
            url = self.files[disk]['links']['self']
            # Unique range query avoids intermediaries reusing a response for another Range.
            with requests.get(url+f'?range={local}-{local+length-1}',headers={'Range':f'bytes={local}-{local+length-1}'},
                              timeout=remaining_timeout(self.deadline),stream=True) as response:
                if response.status_code != 206 or response.headers.get('Content-Range') != expected:
                    raise ValueError('server did not honor bounded range')
                content = response.raw.read(length+1)
                if len(content) != length: raise ValueError('truncated or oversized range')
                remaining_timeout(self.deadline)
            chunks.append(content); offset += length; count -= length
        return b''.join(chunks)

    def extract(self,name):
        entry = self.entries[name]
        header = struct.unpack('<4s5H3I2H',self.read(entry['offset'],30))
        if header[0] != b'PK\x03\x04' or entry['flags'] & 1:
            raise ValueError('invalid or encrypted local entry')
        if entry['size'] > 12*1024*1024: raise ValueError('audio too large')
        payload = self.read(entry['offset']+30+header[9]+header[10],entry['compressed'])
        if entry['method'] == 0: content = payload
        elif entry['method'] == 8: content = zlib.decompress(payload,-15)
        else: raise ValueError('unsupported compression')
        if len(content) != entry['size'] or zlib.crc32(content) & 0xffffffff != entry['crc']:
            raise ValueError('audio CRC mismatch')
        return content


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--split',choices=['dev','eval'],default='eval')
    parser.add_argument('--official-partition', choices=['train', 'val'],
                        help='For dev, select only the official train or val partition')
    parser.add_argument('--per-class',type=int,default=60)
    args = parser.parse_args()
    if not 1 <= args.per_class <= 300: raise ValueError('per-class must be 1..300 (600 clips total)')
    deadline = time.monotonic() + 90 * 60
    split = args.split
    if split == 'eval' and args.official_partition:
        parser.error('--official-partition applies only to dev')
    record = prepare_metadata(deadline)
    metadata = json.loads((ROOT/f'FSD50K.metadata/{split}_clips_info_FSD50K.json').read_text(encoding='utf-8'))
    rows = list(csv.DictReader((ROOT/f'FSD50K.ground_truth/{split}.csv').open(encoding='utf-8')))
    esc = json.loads(Path('artifacts/datasets/esc50/manifest.json').read_text())
    excluded_ids = {r['src_file'] for r in esc['records']+esc['excluded']}
    rows = [r for r in rows if r['fname'] not in excluded_ids and
            any(x in metadata[r['fname']]['license'] for x in ('/by/','/zero/'))]
    if split == 'dev':
        rows = [r for r in rows if r['split']==(args.official_partition or 'train')]
    positive = [r for r in rows if 'Dog' in r['labels'].split(',')]
    negative = [r for r in rows if 'Animal' not in r['labels'].split(',') and 'Dog' not in r['labels'].split(',')]
    order = lambda r:hashlib.sha256(('petmind-fsd-v1:'+r['fname']).encode()).hexdigest()
    selected = sorted(positive,key=order)[:args.per_class]+sorted(negative,key=order)[:args.per_class]
    files = [f for f in record['files'] if f['key'].startswith(f'FSD50K.{split}_audio.')]
    files.sort(key=lambda f:(f['key'].endswith('.zip'),f['key']))
    archive = SplitZip(files, deadline)
    output_name = 'dev_val_subset' if args.official_partition == 'val' else f'{split}_subset'
    output = ROOT/output_name; output.mkdir(exist_ok=True)
    def acquire(row):
        remaining_timeout(deadline)
        name = row['fname']+'.wav'; path = output/name
        if not path.exists():
            content = archive.extract(f'FSD50K.{split}_audio/{name}')
            temporary = path.with_suffix('.partial'); temporary.write_bytes(content); temporary.replace(path)
        info = sf.info(path)
        entry = archive.entries[f'FSD50K.{split}_audio/{name}']
        content = path.read_bytes()
        if zlib.crc32(content) & 0xffffffff != entry['crc']: raise ValueError('cached CRC mismatch')
        return {'filename':name,'source_id':row['fname'],'labels':row['labels'].split(','),
                'expected':int('Dog' in row['labels'].split(',')),
                'sha256':hashlib.sha256(content).hexdigest(),'duration_s':info.duration,
                'license':metadata[row['fname']]['license'],'uploader':metadata[row['fname']]['uploader'],
                'title':metadata[row['fname']]['title'],'split':split,'original_split':row.get('split','eval')}
    records = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for i,item in enumerate(pool.map(acquire,selected),1):
            records.append(item)
            print(f'{split} {i}/{len(selected)}',flush=True)
    manifest = {'source':'https://zenodo.org/records/4060432','records':records,
        'selection':'deterministic hash order; Dog positives, Animal-free negatives; CC0/CC BY; ESC source IDs excluded',
        'scope':'balanced selected subset, not full FSD50K or natural household prevalence',
        'label_policy':'clip-level weak labels; dev negatives may have missing labels; eval official exhaustive annotation',
        'archive_integrity':'per-entry ZIP CRC32 and local SHA256; complete archive not downloaded'}
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print('subset complete',flush=True)


if __name__ == '__main__':
    main()
