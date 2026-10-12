"""Pi USB webcam preview using system FFmpeg; loopback only, no saved frames.

Run: python3 pi_camera_preview.py --device /dev/video0
Forward: ssh -N -L 18081:127.0.0.1:18081 raspberrypi-ai
"""
import argparse
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Frames:
    def __init__(self):
        self.lock = threading.Lock()
        self.jpeg = b''
        self.received = 0.0

    def read(self, pipe):
        buffer = bytearray()
        while chunk := pipe.read(4096):
            buffer.extend(chunk)
            while (end := buffer.find(b'\xff\xd9')) >= 0:
                data = bytes(buffer[:end+2]); del buffer[:end+2]
                start = data.find(b'\xff\xd8')
                if start >= 0:
                    with self.lock:
                        self.jpeg, self.received = data[start:], time.monotonic()
            if len(buffer) > 2*1024*1024:
                buffer.clear()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', default='/dev/video0')
    parser.add_argument('--port', type=int, default=18081)
    args = parser.parse_args()
    frames = Frames()
    process = subprocess.Popen(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'warning',
        '-f', 'v4l2', '-i', args.device, '-an', '-vf', 'fps=2,scale=640:-2',
        '-c:v', 'mjpeg', '-q:v', '5', '-f', 'image2pipe', 'pipe:1'], stdout=subprocess.PIPE)
    threading.Thread(target=frames.read, args=(process.stdout,), daemon=True).start()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != '/snapshot.jpg':
                self.send_error(404); return
            with frames.lock:
                data, received = frames.jpeg, frames.received
            if not data or time.monotonic()-received > 3:
                self.send_error(503, 'Camera unavailable or stale'); return
            self.send_response(200)
            self.send_header('Content-Type', 'image/jpeg')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait()


if __name__ == '__main__':
    main()
