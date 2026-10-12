"""Acquire source-tracked AudioSet strong-label train or evaluation subsets.

Downloaded audio stays under ignored artifacts/. YouTube availability and
rights may differ by source video. Evaluation audio is never used for training.
"""
import argparse
import hashlib
import io
import json
import subprocess
import time
import urllib.request
import wave
from collections import defaultdict
from pathlib import Path

ROOT = Path('artifacts/audioset_bark_strong')
STRONG_URL = ('https://storage.googleapis.com/us_audioset/youtube_corpus/'
              'strong/audioset_train_strong.tsv')
STRONG_EVAL_URL = ('https://storage.googleapis.com/us_audioset/youtube_corpus/'
                   'strong/audioset_eval_strong.tsv')
BARK = '/m/05tny_'
DISTRACTORS = {'/m/03wwcy', '/m/07r4wb8', '/m/09x0r', '/m/07c52'}
SEED = 'petmind-audioset-strong-v1'
TARGET_POSITIVE = 40
TARGET_NEGATIVE = 40
MAX_ATTEMPTS_PER_CLASS = 100


def source_candidates(lines, seed=SEED):
    events = defaultdict(list)
    for line in lines:
        parts = line.rstrip('\n').split('\t')
        if len(parts) != 4:
            continue
        clip_id, start, end, label = parts
        if '_' not in clip_id:
            continue
        try:
            interval = (float(start), float(end), label)
        except ValueError:
            continue
        events[clip_id].append(interval)
    positive, negative = [], []
    for clip_id, intervals in events.items():
        barks = [(start, end) for start, end, label in intervals if label == BARK]
        row = {'clip_id': clip_id, 'video_id': clip_id.rsplit('_', 1)[0],
               'offset_s': int(clip_id.rsplit('_', 1)[1]) / 1000,
               'bark_intervals_s': barks,
               'labels': sorted({label for _, _, label in intervals})}
        if barks:
            positive.append(row)
        elif any(label in DISTRACTORS for _, _, label in intervals):
            negative.append(row)
    key = lambda row: hashlib.sha256((seed + row['clip_id']).encode()).hexdigest()
    return sorted(positive, key=key), sorted(negative, key=key)


def download_clip(row, destination, ffmpeg, root=ROOT):
    import yt_dlp

    source = root/'downloads'/row['video_id']
    source.parent.mkdir(parents=True, exist_ok=True)
    options = {'format': 'bestaudio[ext=m4a]/bestaudio', 'outtmpl': str(source)+'.%(ext)s',
               'quiet': True, 'no_warnings': True, 'noprogress': True, 'noplaylist': True,
               'socket_timeout': 12, 'retries': 1, 'extractor_retries': 1,
               'match_filter': yt_dlp.utils.match_filter_func('duration <= 90')}
    with yt_dlp.YoutubeDL(options) as downloader:
        downloader.download(['https://www.youtube.com/watch?v='+row['video_id']])
    audio = next(source.parent.glob(source.name+'.*'), None)
    if audio is None:
        raise FileNotFoundError('no downloaded audio')
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg, '-nostdin', '-loglevel', 'error', '-y',
                    '-ss', str(row['offset_s']), '-i', str(audio), '-t', '10',
                    '-ac', '1', '-ar', '16000', str(destination)],
                   check=True, timeout=30)
    audio.unlink()
    with wave.open(str(destination)) as wav:
        duration = wav.getnframes()/wav.getframerate()
    if duration < 9.8:
        destination.unlink(missing_ok=True)
        raise ValueError(f'audio shorter than expected: {duration:.2f}s')


def complete_wav(path):
    if not path.exists():
        return False
    with wave.open(str(path)) as wav:
        return wav.getframerate() == 16000 and wav.getnframes()/16000 >= 9.8


def validate_existing(root=ROOT, split='train'):
    path = root/'manifest.json'
    manifest = json.loads(path.read_text(encoding='utf-8'))
    accepted = []
    for row in manifest['rows'][split]:
        source = Path(row['path'])
        if complete_wav(source) and hashlib.sha256(source.read_bytes()).hexdigest() == row['sha256']:
            accepted.append(row)
        else:
            manifest['failures'].append({'clip_id': row['clip_id'],
                                         'reason': 'incomplete or changed WAV during validation'})
            source.unlink(missing_ok=True)
    manifest['rows'][split] = accepted
    path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print({'validated': len(accepted), 'excluded': len(manifest['failures'])}, flush=True)


def main(split='train', target_positive=TARGET_POSITIVE, target_negative=TARGET_NEGATIVE):
    import imageio_ffmpeg

    root = ROOT if split == 'train' else Path('artifacts/audioset_bark_strong_eval')
    url = STRONG_URL if split == 'train' else STRONG_EVAL_URL
    seed = SEED if split == 'train' else SEED+'-eval'
    root.mkdir(parents=True, exist_ok=True)
    raw = urllib.request.urlopen(url, timeout=60).read()
    (root/f'audioset_{split}_strong.sha256').write_text(
        hashlib.sha256(raw).hexdigest()+'\n', encoding='ascii')
    positive, negative = source_candidates(io.StringIO(raw.decode('utf-8')), seed)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    start = time.monotonic()
    selected, failures, used_videos = [], [], set()
    for group, target in [(positive, target_positive), (negative, target_negative)]:
        accepted = 0
        for row in group[:MAX_ATTEMPTS_PER_CLASS]:
            if accepted >= target:
                break
            if row['video_id'] in used_videos:
                continue
            destination = root/'audio'/(row['clip_id']+'.wav')
            try:
                if not complete_wav(destination):
                    destination.unlink(missing_ok=True)
                    download_clip(row, destination, ffmpeg, root)
                row['sha256'] = hashlib.sha256(destination.read_bytes()).hexdigest()
                row['path'] = str(destination.resolve())
                selected.append(row)
                used_videos.add(row['video_id'])
                accepted += 1
                print(f'{"bark" if group is positive else "negative"} {accepted}/{target}: '
                      f'{row["clip_id"]}', flush=True)
            except Exception as exc:
                failures.append({'clip_id': row['clip_id'], 'reason': str(exc)[:200]})
                destination.unlink(missing_ok=True)
    manifest = {'source': url, 'source_sha256': hashlib.sha256(raw).hexdigest(),
                'scope': f'AudioSet strong-label {split} only',
                'selection': f'deterministic {seed}, up to {target_positive} Bark and '
                             f'{target_negative} distractor clips; unique YouTube IDs',
                'positive_candidates': len(positive),
                'negative_candidates': len(negative),
                'rows': {split: selected}, 'failures': failures,
                'elapsed_s': time.monotonic()-start}
    (root/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    validate_existing(root, split)
    print({'downloaded': len(selected), 'bark': sum(bool(r['bark_intervals_s']) for r in selected),
           'failed': len(failures), 'elapsed_s': round(manifest['elapsed_s'], 1)}, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--split', choices=['train', 'eval'], default='train')
    parser.add_argument('--positive', type=int, default=TARGET_POSITIVE)
    parser.add_argument('--negative', type=int, default=TARGET_NEGATIVE)
    parser.add_argument('--validate-existing', action='store_true')
    args = parser.parse_args()
    if args.validate_existing:
        validate_existing(ROOT if args.split == 'train' else Path('artifacts/audioset_bark_strong_eval'), args.split)
    else:
        main(args.split, args.positive, args.negative)
