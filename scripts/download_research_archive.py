"""Resumable byte-range download from the publisher's public dataset URLs."""
import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
import truststore

truststore.inject_into_ssl()  # Use the Windows certificate store for university hosts.

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/141.0.0.0 Safari/537.36',
           'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
           'Accept-Encoding': 'identity', 'Accept-Language': 'en-US,en;q=0.9',
           'Referer': 'https://calvin-vision.net/datasets/tigdog/'}
ARCHIVES = {'tigdog': ('https://calvin-vision.net/bigstuff/tigdog/dog.tar.gz', 'dog.tar.gz'),
            'yto_videos': ('https://calvin-vision.net/bigstuff/youtube-objectsv2/videos/YouTubeObjectsVideos.tar.gz', 'YTO_videos.tar.gz'),
            'a2d': ('https://web.eecs.umich.edu/~jjcorso/bigshare/A2D_main_1_0.tar.bz', 'A2D_main_1_0.tar.bz'),
            'a2d_eval': ('https://web.eecs.umich.edu/~jjcorso/bigshare/A2D_eval_1_0.tar.bz', 'A2D_eval_1_0.tar.bz')}


def download(kind, workers=8):
    url, filename = ARCHIVES[kind]
    path = Path('artifacts/datasets/a2d' if kind.startswith('a2d') else 'artifacts/datasets/tigdog') / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix('.ranges.part')
    state_path = path.with_suffix('.ranges.json')
    headers = HEADERS | ({'Referer': 'https://web.eecs.umich.edu/~jjcorso/r/a2d/'} if kind.startswith('a2d') else {})
    with requests.get(url, headers=headers | {'Range': 'bytes=0-0'}, stream=True, timeout=30) as response:
        response.raise_for_status()
        if response.status_code != 206:
            raise ValueError('publisher does not support byte ranges')
        size = int(response.headers['Content-Range'].split('/')[-1])
        etag = response.headers.get('ETag')
    if path.exists():
        if path.stat().st_size != size:
            raise ValueError(f'{filename}: incomplete existing archive ({path.stat().st_size}/{size} bytes)')
        print(f'{filename}: existing archive ({size} bytes)', flush=True)
        return
    chunk_size = 8*1024*1024
    state = {'url': url, 'size': size, 'etag': etag, 'chunk_size': chunk_size, 'completed': []}
    if state_path.exists():
        previous = json.loads(state_path.read_text())
        if any(previous[key] != state[key] for key in ['url', 'size', 'etag', 'chunk_size']):
            raise ValueError('publisher version changed; do not mix archive versions')
        state = previous
    completed = set(state['completed'])
    def fetch(index):
        start, end = index*chunk_size, min(size-1, (index+1)*chunk_size-1)
        with requests.get(url, headers=headers | {'Range': f'bytes={start}-{end}'}, timeout=120) as response:
            response.raise_for_status()
            if response.status_code != 206 or response.headers.get('Content-Range') != f'bytes {start}-{end}/{size}':
                raise ValueError('range response mismatch')
            if response.headers.get('ETag') != etag or len(response.content) != end-start+1:
                raise ValueError('range version/length mismatch')
            return index, response.content
    indices = [i for i in range((size+chunk_size-1)//chunk_size) if i not in completed]
    with part.open('r+b' if part.exists() else 'w+b') as stream, ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fetch, index) for index in indices]
        for future in as_completed(futures):
            index, content = future.result()
            stream.seek(index*chunk_size); stream.write(content); stream.flush()
            completed.add(index); state['completed'] = sorted(completed)
            state_path.write_text(json.dumps(state), encoding='utf-8')
            if len(completed) % 16 == 0 or len(completed) == (size+chunk_size-1)//chunk_size:
                print(f'{filename}: {len(completed)*chunk_size//1024//1024}/{size//1024//1024} MiB', flush=True)
    digest = hashlib.file_digest(part.open('rb'), 'sha256').hexdigest()
    part.replace(path)
    state['sha256'] = digest
    state_path.write_text(json.dumps(state, indent=2), encoding='utf-8')
    print(f'{filename}: complete sha256={digest}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('kind', choices=ARCHIVES)
    parser.add_argument('--workers', type=int, default=8)
    args = parser.parse_args(); download(args.kind, args.workers)
