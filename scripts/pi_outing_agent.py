"""Poll automatic outings on Pi; one camera owner for capture and preview.

Run from repo root with --pet-id and --input-args-file (FFmpeg device JSON).
Use an SSH reverse tunnel to the PC API. No GPIO or sound output.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
import requests

CLOCK_TOLERANCE_SECONDS = 2.0


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
        '--preview-file', str(folder/'preview.jpg')]


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


def serve_preview(folder, port):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != '/snapshot.jpg': self.send_error(404); return
            try:
                path=folder/'preview.jpg'
                if time.time()-path.stat().st_mtime > 12: raise OSError('stale')
                data=path.read_bytes()
            except OSError:
                self.send_error(503, 'Capture inactive or stale'); return
            self.send_response(200)
            self.send_header('Content-Type','image/jpeg')
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(data)))
            self.end_headers()
            try: self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError): pass
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    return server


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',default='http://127.0.0.1:18010')
    parser.add_argument('--pet-id',required=True)
    parser.add_argument('--input-args-file',type=Path,required=True)
    parser.add_argument('--ffmpeg',default='ffmpeg')
    parser.add_argument('--video-map',default='0:v:0')
    parser.add_argument('--audio-map',default='1:a:0')
    parser.add_argument('--preview-port',type=int,default=18081)
    args=parser.parse_args()
    owner=uuid.uuid4().hex
    def post(route, state='starting'):
        sent_at=time.time()
        result=requests.post(args.base.rstrip('/')+route,
            json={'pet_id':args.pet_id,'owner':owner,'state':state},timeout=8)
        received_at=time.time()
        result.raise_for_status()
        return result.json(), sent_at, received_at
    with tempfile.TemporaryDirectory(prefix='petmind-agent-') as temp:
        folder=Path(temp); server=serve_preview(folder,args.preview_port)
        process=None
        try:
            while True:
                try: claim, sent_at, received_at=post('/capture/claim'); job=claim['job']
                except requests.RequestException:
                    time.sleep(3); continue
                if not job:
                    time.sleep(3); continue
                for name in ('stop','progress.json','preview.jpg'):
                    (folder/name).unlink(missing_ok=True)
                route=f"/capture/{job['outing_id']}/heartbeat"
                if not clock_healthy(claim['server_time'],sent_at,received_at):
                    print('PC/Pi clock mismatch or slow connection; synchronize clocks before capture.',flush=True)
                    try: post(route,'clock_mismatch')
                    except requests.RequestException: pass
                    continue
                stop_at=None
                clock_bad=False
                try:
                    process=subprocess.Popen(worker_command(args,job,folder),start_new_session=True)
                    while process.poll() is None:
                        state='starting'
                        try:
                            progress=json.loads((folder/'progress.json').read_text(encoding='utf-8'))
                            if time.time()-progress['at']<20:
                                state='capturing' if progress['model_ready'] else 'model_unavailable'
                        except (OSError,ValueError,KeyError): pass
                        try:
                            reply, sent_at, received_at=post(route,'draining' if stop_at else state)
                            stop=reply.get('stop',False)
                            if not clock_healthy(reply['server_time'],sent_at,received_at):
                                clock_bad=True; stop=True
                        except requests.RequestException: stop=True
                        if stop and stop_at is None:
                            (folder/'stop').touch(); stop_at=time.monotonic()
                        if stop_at and time.monotonic()-stop_at>150:
                            terminate_tree(process); break
                        time.sleep(2)
                    final=('clock_mismatch' if clock_bad else
                           'stopped' if stop_at and process.returncode==0 else 'failed')
                    try: post(route,final)
                    except requests.RequestException: pass
                except OSError:
                    try: post(route,'failed')
                    except requests.RequestException: pass
                finally:
                    if process: terminate_tree(process)
                    process=None
                    (folder/'preview.jpg').unlink(missing_ok=True)
        except KeyboardInterrupt:
            pass
        finally:
            if process: terminate_tree(process)
            server.shutdown(); server.server_close()


if __name__=='__main__': main()
