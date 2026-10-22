"""수집 프로그램이 FFmpeg에서 받은 JPEG 프레임을 로컬 HTTP로 내보낸다(저장하지 않는다).

FFmpeg의 두 번째 출력(image2pipe, mjpeg)을 표준 출력으로 받아 프레임 단위로 자르고(FrameSplitter),
최신 프레임만 메모리에 둔 채(FrameHub) 127.0.0.1에서 두 주소를 제공한다.

    GET /snapshot.jpg  최신 프레임 1장(12초 넘게 갱신이 없으면 503)
    GET /stream        multipart/x-mixed-replace MJPEG 스트림(프레임이 생기는 대로 밀어 준다)

백엔드의 /camera/stream이 이 스트림을 그대로 전달하고, 화면은 <img src="/camera/stream"> 하나로 받는다.
"""
from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SOI = b"\xff\xd8"
EOI = b"\xff\xd9"
BOUNDARY = "petmindframe"
STALE_SECONDS = 12.0
MAX_BUFFER = 8 * 1024 * 1024


class FrameSplitter:
    """이어 붙은 JPEG 바이트 흐름에서 프레임(SOI~EOI) 단위로 잘라 낸다.

    JPEG 데이터 안의 0xFF는 0x00으로 채워지므로 0xFFD9는 프레임 끝에만 나온다(썸네일이 없는 FFmpeg 출력 기준).
    """

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        self._buf += data
        frames: list[bytes] = []
        while True:
            start = self._buf.find(SOI)
            if start < 0:
                del self._buf[:-1]  # 마커의 절반(0xFF)일 수 있어 마지막 1바이트만 남긴다
                break
            end = self._buf.find(EOI, start + 2)
            if end < 0:
                if start:
                    del self._buf[:start]
                break
            frames.append(bytes(self._buf[start:end + 2]))
            del self._buf[:end + 2]
        if len(self._buf) > MAX_BUFFER:  # 끝나지 않는 프레임이 쌓이는 것을 막는다
            self._buf.clear()
        return frames


class FrameHub:
    """최신 프레임 하나를 보관하고 새 프레임을 기다리는 스레드를 깨운다."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._frame: bytes | None = None
        self._seq = 0
        self._at = 0.0

    def publish(self, frame: bytes) -> None:
        with self._cond:
            self._frame, self._at = frame, time.monotonic()
            self._seq += 1
            self._cond.notify_all()

    def latest(self, max_age: float = STALE_SECONDS) -> bytes | None:
        with self._cond:
            if self._frame is None or time.monotonic() - self._at > max_age:
                return None
            return self._frame

    def wait_next(self, last_seq: int, timeout: float = 2.0) -> tuple[int, bytes | None]:
        """last_seq 이후의 새 프레임을 기다린다. 시간이 지나면 (last_seq, None)."""
        with self._cond:
            self._cond.wait_for(lambda: self._seq != last_seq, timeout)
            if self._seq == last_seq:
                return last_seq, None
            return self._seq, self._frame

    @property
    def sequence(self) -> int:
        with self._cond:
            return self._seq


def pump(stream, hub: FrameHub) -> None:
    """FFmpeg 표준 출력에서 읽은 바이트를 프레임으로 잘라 hub에 올린다(스트림이 닫히면 끝난다)."""
    splitter = FrameSplitter()
    read = getattr(stream, "read1", stream.read)
    while True:
        try:
            data = read(65536)
        except (OSError, ValueError):
            return
        if not data:
            return
        for frame in splitter.feed(data):
            hub.publish(frame)


def make_handler(hub: FrameHub):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # 요청마다 로그를 남기지 않는다
            pass

        def do_GET(self) -> None:
            if self.path == "/snapshot.jpg":
                frame = hub.latest()
                if frame is None:
                    self.send_error(503, "Capture inactive or stale")
                    return
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(frame)))
                self.end_headers()
                self._write(frame)
            elif self.path == "/stream":
                self.send_response(200)
                self.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={BOUNDARY}")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                seq = 0
                idle = 0
                while True:
                    seq, frame = hub.wait_next(seq, timeout=2.0)
                    if frame is None:
                        idle += 1
                        if idle >= 5:  # 10초 동안 새 프레임이 없으면 연결을 닫는다
                            return
                        continue
                    idle = 0
                    head = (f"--{BOUNDARY}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(frame)}\r\n\r\n").encode()
                    if not self._write(head + frame + b"\r\n"):
                        return
            else:
                self.send_error(404)

        def _write(self, data: bytes) -> bool:
            try:
                self.wfile.write(data)
                self.wfile.flush()
                return True
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                return False

    return Handler


def start_preview_server(hub: FrameHub, port: int, host: str = "127.0.0.1") -> ThreadingHTTPServer:
    """로컬 전용 서버를 백그라운드 스레드로 시작한다. port=0이면 빈 포트를 쓴다(server.server_address[1])."""
    server = ThreadingHTTPServer((host, port), make_handler(hub))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
