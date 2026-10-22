"""Poll automatic outings and run the capture program (webcam + microphone) for each; it also serves the live camera view.

Run from repo root with --pet-id and --input-args-file (FFmpeg device JSON).
Runs on the same PC as the backend. No GPIO or sound output.

If the capture program exits unexpectedly (device unplugged, FFmpeg crash, stalled microphone) it is restarted
up to MAX_RESTARTS times; the gap stays visible as unobserved time in the outing summary. A brief backend outage
does not stop capture either: it stops only after HEARTBEAT_FAILURES_BEFORE_STOP failed heartbeats in a row.

With --redetect the devices are looked up again before every (re)start, so a replugged or renamed camera/microphone is
picked up. While one is missing the job stays in 'starting' for up to DEVICE_WAIT_SECONDS; that wait does not use up restarts.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
import requests

CLOCK_TOLERANCE_SECONDS = 2.0
MAX_RESTARTS = 5               # consecutive unexpected capture exits before the job is marked failed
RESTART_BACKOFF_SECONDS = 5    # waits 5 s, 10 s, ... between restarts (heartbeats continue meanwhile)
HEALTHY_RUN_SECONDS = 60       # a worker that ran this long resets the restart counter
HEARTBEAT_FAILURES_BEFORE_STOP = 10   # consecutive failed heartbeats (about 20+ s) before capture is stopped
STOP_GRACE_SECONDS = 150
DEVICE_WAIT_SECONDS = 300      # with --redetect: how long to wait for an unplugged camera/microphone before failing
DEVICE_POLL_SECONDS = 5


def clock_healthy(server_time, sent_at, received_at):
    """Estimate offset at the request midpoint; reject slow or skewed probes."""
    server = datetime.fromisoformat(server_time.replace('Z', '+00:00')).astimezone(timezone.utc).timestamp()
    return (received_at >= sent_at and received_at-sent_at <= CLOCK_TOLERANCE_SECONDS
            and abs(server-(sent_at+received_at)/2) <= CLOCK_TOLERANCE_SECONDS)


def worker_command(args, job, folder):
    return [sys.executable, '-m', 'scripts.monitor_audio_events',
        '--base', args.base, '--pet-id', args.pet_id, '--outing-id', job['outing_id'],
        '--input-args-file', str(args.input_args_file.resolve()), '--ffmpeg', args.ffmpeg,
        '--video-map', args.video_map, '--audio-map', args.audio_map, '--store-consent',
        '--stop-file', str(folder/'stop'), '--progress-file', str(folder/'progress.json'),
        '--preview-port', str(args.preview_port)]


def terminate_tree(process):
    if os.name == 'posix':
        try: os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError: pass
    else:
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
    try: process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name == 'posix': os.killpg(process.pid, signal.SIGKILL)
        else: process.kill()
        process.wait()


def worker_state(folder):
    """capturing / model_unavailable from the worker's progress file, otherwise starting."""
    try:
        progress=json.loads((folder/'progress.json').read_text(encoding='utf-8'))
        if time.time()-progress['at']<20:
            return 'capturing' if progress['model_ready'] else 'model_unavailable'
    except (OSError,ValueError,KeyError): pass
    return 'starting'


def supervise(args, job, folder, post, route, popen=subprocess.Popen, sleep=time.sleep, monotonic=time.monotonic, redetect=None):
    """Run the capture worker for one outing and keep it alive. Returns the final state to report:
    stopped, failed or clock_mismatch."""
    stop_at=None; clock_bad=False; failures=0; restarts=0; process=None

    def beat(state):
        nonlocal stop_at, clock_bad, failures
        try:
            reply, sent_at, received_at=post(route,'draining' if stop_at else state)
            failures=0
            stop=reply.get('stop',False)
            if not clock_healthy(reply['server_time'],sent_at,received_at):
                clock_bad=True; stop=True
        except requests.RequestException:
            failures+=1
            stop=failures>=HEARTBEAT_FAILURES_BEFORE_STOP
        if stop and stop_at is None:
            (folder/'stop').touch(); stop_at=monotonic()

    def found():
        try: return bool(redetect())
        except Exception: return False   # a failed lookup counts as "not found yet", never as a crash of the agent

    def devices_ready():
        """True when capture may start. With redetect, waits (sending heartbeats) until the devices are present."""
        if redetect is None or found(): return True
        deadline=monotonic()+DEVICE_WAIT_SECONDS
        print('camera or microphone not found; waiting for it to be connected',flush=True)
        while stop_at is None and monotonic()<deadline:
            beat('starting'); sleep(DEVICE_POLL_SECONDS)
            if stop_at is None and found(): return True
        return False

    try:
        while True:
            if not devices_ready():
                if clock_bad: return 'clock_mismatch'
                return 'stopped' if stop_at is not None else 'failed'
            try: process=popen(worker_command(args,job,folder),start_new_session=True)
            except OSError: return 'failed'
            run_started=monotonic()
            while process.poll() is None:
                beat(worker_state(folder))
                if stop_at and monotonic()-stop_at>STOP_GRACE_SECONDS:
                    terminate_tree(process); break
                sleep(2)
            if clock_bad: return 'clock_mismatch'
            if stop_at is not None:
                return 'stopped' if process.returncode==0 else 'failed'
            # The capture program ended without being asked to: restart it unless it keeps failing.
            if monotonic()-run_started>=HEALTHY_RUN_SECONDS: restarts=0
            restarts+=1
            print(f'capture program exited ({process.returncode}); restart {restarts}/{MAX_RESTARTS}',flush=True)
            if restarts>MAX_RESTARTS: return 'failed'
            terminate_tree(process); process=None
            wait_until=monotonic()+RESTART_BACKOFF_SECONDS*restarts
            while monotonic()<wait_until and stop_at is None:
                beat('starting'); sleep(2)
            if clock_bad: return 'clock_mismatch'
            if stop_at is not None: return 'stopped'
    finally:
        if process: terminate_tree(process)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',default='http://127.0.0.1:8010')
    parser.add_argument('--pet-id',required=True)
    parser.add_argument('--input-args-file',type=Path,required=True)
    parser.add_argument('--ffmpeg',default='ffmpeg')
    parser.add_argument('--video-map',default='0:v:0')
    parser.add_argument('--audio-map',default='1:a:0')
    parser.add_argument('--preview-port',type=int,default=18081)
    parser.add_argument('--redetect',action='store_true',help='look the camera/microphone up again before every (re)start (Windows DirectShow)')
    parser.add_argument('--video-hint',help='part of the camera name to prefer when redetecting')
    parser.add_argument('--audio-hint',help='part of the microphone name to prefer when redetecting')
    args=parser.parse_args()
    owner=uuid.uuid4().hex
    def post(route, state='starting'):
        sent_at=time.time()
        result=requests.post(args.base.rstrip('/')+route,
            json={'pet_id':args.pet_id,'owner':owner,'state':state},timeout=8)
        received_at=time.time()
        result.raise_for_status()
        return result.json(), sent_at, received_at
    redetect=None
    if args.redetect:
        from scripts import make_capture_input
        redetect=lambda: make_capture_input.refresh(args.ffmpeg,args.input_args_file,args.video_hint,args.audio_hint)
    with tempfile.TemporaryDirectory(prefix='petmind-agent-') as temp:
        folder=Path(temp)
        try:
            while True:
                try: claim, sent_at, received_at=post('/capture/claim'); job=claim['job']
                except requests.RequestException:
                    time.sleep(3); continue
                if not job:
                    time.sleep(3); continue
                for name in ('stop','progress.json'):
                    (folder/name).unlink(missing_ok=True)
                route=f"/capture/{job['outing_id']}/heartbeat"
                if not clock_healthy(claim['server_time'],sent_at,received_at):
                    print('PC clock mismatch or slow connection; synchronize clocks before capture.',flush=True)
                    try: post(route,'clock_mismatch')
                    except requests.RequestException: pass
                    continue
                final=supervise(args,job,folder,post,route,redetect=redetect)
                try: post(route,final)
                except requests.RequestException: pass
        except KeyboardInterrupt:
            pass


if __name__=='__main__': main()
