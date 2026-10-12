"""Extract only the public archive's 24 dog videos as its prefix arrives.

The download can be stopped after extraction; irrelevant later animal videos
are not needed. Hash each dog clip separately; no full-archive hash is claimed.
"""
import hashlib
import json
import re
import tarfile
import time
from pathlib import Path

ROOT = Path('artifacts/datasets/tigdog')


class DownloadPrefix:
    def __init__(self):
        self.state_path = ROOT/'YTO_videos.tar.ranges.json'
        self.path = ROOT/'YTO_videos.tar.ranges.part'
        self.position = 0
        self.available = 0
        self.last_progress = time.monotonic()
        self.stream = self.path.open('rb')

    def read(self, amount):
        while self.available <= self.position:
            try:
                state = json.loads(self.state_path.read_text())
                done = set(state['completed']); count = 0
                while count in done:
                    count += 1
                available = min(state['size'], count*state['chunk_size'])
                if available > self.available:
                    self.available = available; self.last_progress = time.monotonic()
                if self.position == state['size']:
                    return b''
            except (FileNotFoundError, json.JSONDecodeError):
                pass
            if time.monotonic()-self.last_progress > 180:
                raise TimeoutError('archive prefix download stalled')
            if self.available <= self.position:
                time.sleep(1)
        data = self.stream.read(min(amount, self.available-self.position))
        self.position += len(data)
        return data


def run():
    destination = ROOT/'original_dog_videos'; destination.mkdir(parents=True, exist_ok=True)
    prefix = DownloadPrefix(); records = []
    try:
        with tarfile.open(fileobj=prefix, mode='r|gz') as archive:
            for member in archive:
                if not member.isfile() or not re.search(r'(?:\s|/)dog/', member.name.lower()):
                    continue
                if not member.name.lower().endswith(('.mp4', '.avi', '.flv')):
                    continue
                target = destination/Path(member.name).name
                digest = hashlib.sha256()
                with archive.extractfile(member) as source, target.open('wb') as stream:
                    while chunk := source.read(1024*1024):
                        digest.update(chunk); stream.write(chunk)
                records.append({'archive_member': member.name, 'filename': target.name,
                                'bytes': member.size, 'sha256': digest.hexdigest()})
                print(f'dog videos extracted: {len(records)}/24 ({target.name})', flush=True)
                if len(records) == 24:
                    break
    finally:
        prefix.stream.close()
    if len(records) != 24:
        raise ValueError('dog video count differs from publisher ranges')
    (destination/'extracted.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
    (destination/'source.json').write_text(json.dumps({
        'url': 'https://calvin-vision.net/bigstuff/youtube-objectsv2/videos/YouTubeObjectsVideos.tar.gz',
        'compressed_prefix_bytes_read': prefix.position, 'full_archive_downloaded': False,
        'files': len(records), 'integrity': 'publisher tar headers + per-clip local SHA256; no complete gzip CRC claimed'
    }, indent=2), encoding='utf-8')


if __name__ == '__main__':
    run()
