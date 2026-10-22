r"""Live end-to-end check: laptop speaker -> built-in microphone -> capture agent -> YAMNet -> event video.

Plays ESC-50 clips (prepare with `python -m scripts.prepare_demo_audio`, peak-normalised so they are loud) through the
default playback device while an automatic outing records the built-in microphone and webcam, then prints, per 5 s
segment, the YAMNet Bark score next to the sound that was playing, checks the saved event video with FFmpeg, and
deletes every original (audio and video) of the test outing.

    .\.venv\Scripts\python.exe -m scripts.live_bark_check --play          # 4 sounds, about 2.5 minutes
    .\.venv\Scripts\python.exe -m scripts.live_bark_check --play --short  # 2 dog clips only

Needs `start_demo.ps1 -Capture` running. It makes loud sound and records the room: pass --play to confirm.
Set the default playback device to the laptop speakers and turn off the microphone array's "audio enhancements"
(echo cancellation removes the laptop's own speaker output from the microphone signal). Results are logged to
artifacts/demo/live_bark_test.log/.json (git-ignored). A handful of clips is a functional check, not an accuracy test.
"""
import sys
if '--play' not in sys.argv:
    raise SystemExit('This plays loud sound and records the microphone and webcam. Re-run with --play to confirm.')
import json, os, re, subprocess, sys, tempfile, time, winsound
from datetime import datetime, timedelta, timezone
import numpy as np
import requests
import soundfile as sf

BASE, PET = 'http://127.0.0.1:8010', 'demo-dog'
CFG = json.load(open('artifacts/demo/capture-config.json', encoding='utf-8'))
AUDIO = 'artifacts/datasets/esc50_demo/audio'
FULL = [('dog_A  5-208030 (orig .843)', '5-208030-A-0'), ('rain   5-181766 (orig 0)', '5-181766-A-10'),
        ('dog_B  5-203128 (orig .842)', '5-203128-A-0'), ('dog_C  1-100032 (orig .299)', '1-100032-A-0')]
PLAN = FULL if not '--short' in sys.argv else [FULL[0], FULL[2]]
GAP = 10          # silence between sounds (seconds)
tmp = tempfile.mkdtemp(prefix='petmind-live-')
out = open('artifacts/demo/live_bark_test.log', 'w', encoding='utf-8')


def log(*a):
    line = ' '.join(str(x) for x in a); print(line, flush=True); out.write(line + '\n'); out.flush()


def loud(name):
    x, sr = sf.read(f'{AUDIO}/{name}.wav', dtype='float32')
    p = os.path.join(tmp, name + '.wav'); sf.write(p, (x / np.abs(x).max() * 0.95).astype('float32'), sr)
    return p, len(x) / sr


oid = requests.post(f'{BASE}/outings', json={'pet_id': PET, 'input_mode': 'live', 'title': '실제 소리 시험',
                                            'auto_capture': True, 'store_consent': True}, timeout=20).json()['id']
log('outing', oid)
for _ in range(60):
    st = requests.get(f'{BASE}/capture/{oid}', params={'pet_id': PET}, timeout=10).json()['state']
    if st == 'capturing': break
    time.sleep(2)
log('capture state:', st)
time.sleep(12)   # a few quiet segments first

plays = []       # (label, start_utc, end_utc)
for label, name in PLAN:
    path, dur = loud(name)
    start = datetime.now(timezone.utc)
    winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
    log('play', label, start.isoformat())
    time.sleep(dur)
    plays.append((label, start, start + timedelta(seconds=dur)))
    time.sleep(GAP)
time.sleep(15)   # lets the last event's 5 s tail close
requests.post(f'{BASE}/outings/{oid}/end', params={'pet_id': PET}, timeout=30)
for _ in range(60):
    st = requests.get(f'{BASE}/capture/{oid}', params={'pet_id': PET}, timeout=10).json()['state']
    if st in ('stopped', 'failed', 'clock_mismatch'): break
    time.sleep(3)
log('final capture state:', st)

summary = requests.get(f'{BASE}/outings/{oid}/summary', params={'pet_id': PET}, timeout=30).json()
result = {'outing': oid, 'final_state': st, 'plays': [], 'segments': [], 'event_videos': []}
segs = []
for m in summary['moments']:
    clip_id = re.search(r'/audio-clips/([0-9a-f]+)/', m['audio_url'] or '')
    segs.append((m, clip_id.group(1) if clip_id else None))
detail = {c['id']: c for c in requests.get(f'{BASE}/audio-clips', params={'pet_id': PET, 'limit': 500}, timeout=60).json()}
rows = []
for m, cid in segs:
    c = detail.get(cid)
    if not c: continue
    cap = c['analysis'].get('capture', {})
    s = datetime.fromisoformat(cap['started_at']); e = s + timedelta(seconds=c['duration_s'])
    score = (c['analysis'].get('audio_model') or {}).get('dog_score')
    rows.append((s, e, score, m, cid))
rows.sort(key=lambda r: r[0])
t0 = plays[0][1]
log('\n-- sounds played (seconds after the first sound)')
for label, s, e in plays:
    log('  %-30s %5.1f - %5.1f' % (label, (s - t0).total_seconds(), (e - t0).total_seconds()))
log('\n-- stored 5 s segments: start offset, YAMNet bark score, overlapping sound, event video')
for s, e, score, m, cid in rows:
    ov = [lbl.split()[0] for lbl, ps, pe in plays if ps < e and pe > s]
    ev = (m.get('event_video') or {}).get('status')
    log('  %6.1f  score=%-6s overlap=%-14s event_video=%s' % ((s - t0).total_seconds(), score, ','.join(ov) or '-', ev))
    result['segments'].append({'offset_s': round((s - t0).total_seconds(), 1), 'score': score, 'overlap': ov, 'event_video': ev})

log('\n-- per sound: best score among overlapping segments (threshold 0.05)')
for label, ps, pe in plays:
    sc = [r[2] for r in rows if r[0] < pe and r[1] > ps and r[2] is not None]
    best = max(sc) if sc else None
    log('  %-30s best=%s  detected=%s' % (label, best, (best or 0) >= 0.05))
    result['plays'].append({'label': label, 'best_score': best, 'detected': (best or 0) >= 0.05})
quiet = [r[2] for r in rows if not any(ps < r[1] and pe > r[0] for _, ps, pe in plays) and r[2] is not None]
log('quiet segments (no sound playing): n=%d, max score=%s' % (len(quiet), max(quiet) if quiet else None))
result['quiet_max'] = max(quiet) if quiet else None

log('\n-- event videos')
for s, e, score, m, cid in rows:
    if m.get('media_available') and m.get('clip_url'):
        r = requests.get(f"{BASE}/outings/observations/{m['observation_id']}/video", params={'pet_id': PET}, timeout=60)
        path = os.path.join(tmp, f'ev_{cid}.mp4'); open(path, 'wb').write(r.content)
        info = subprocess.run([CFG['ffmpeg'], '-hide_banner', '-i', path], capture_output=True, text=True).stderr
        d = re.search(r'Duration: (\d+):(\d+):([\d.]+)', info)
        dur = int(d.group(1)) * 3600 + int(d.group(2)) * 60 + float(d.group(3)) if d else None
        vid = re.search(r'Video: (\w+).*?(\d+x\d+)', info); aud = re.search(r'Audio: (\w+)', info)
        png = os.path.join(tmp, f'f_{cid}.png')
        subprocess.run([CFG['ffmpeg'], '-hide_banner', '-loglevel', 'error', '-y', '-ss', '1', '-i', path, '-frames:v', '1', png])
        bright = None
        if os.path.exists(png):
            import cv2; img = cv2.imread(png); bright = round(float(img.mean()), 1) if img is not None else None
        log('  segment %+.1fs  http=%s type=%s bytes=%d duration=%ss video=%s audio=%s frame_mean_brightness=%s' % (
            (s - t0).total_seconds(), r.status_code, r.headers.get('content-type'), len(r.content), dur, vid.groups() if vid else None, aud.group(1) if aud else None, bright))
        result['event_videos'].append({'offset_s': round((s - t0).total_seconds(), 1), 'duration_s': dur, 'bytes': len(r.content), 'audio': bool(aud), 'frame_brightness': bright})

# cleanup: delete every original of this outing (audio; linked event videos go with them)
deleted = 0
for s, e, score, m, cid in rows:
    if cid:
        requests.post(f'{BASE}/audio-clips/{cid}/delete-original', params={'pet_id': PET}, timeout=30).raise_for_status(); deleted += 1
after = requests.get(f'{BASE}/outings/{oid}/summary', params={'pet_id': PET}, timeout=30).json()
left = sum(1 for m in after['moments'] if m.get('audio_available') or m.get('media_available'))
log('\ncleanup: deleted %d originals; originals/videos still available: %d' % (deleted, left))
json.dump(result, open('artifacts/demo/live_bark_test.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
import shutil; shutil.rmtree(tmp, ignore_errors=True)
