import io
import threading
import time
import unittest

import requests

from scripts.preview_stream import FrameHub, FrameSplitter, pump, start_preview_server


def jpeg(n: int) -> bytes:
    return b"\xff\xd8" + bytes([n]) * 20 + b"\xff\x00\xff\xd9"  # 데이터 안의 FF는 00으로 채워진다


class FrameSplitterTests(unittest.TestCase):
    def test_splits_concatenated_frames(self):
        frames = FrameSplitter().feed(jpeg(1) + jpeg(2) + jpeg(3))
        self.assertEqual(frames, [jpeg(1), jpeg(2), jpeg(3)])

    def test_frame_split_across_chunks_is_reassembled(self):
        s = FrameSplitter()
        data = jpeg(7) + jpeg(8)
        out = []
        for i in range(0, len(data), 5):  # 5바이트씩 쪼개 넣는다(마커가 경계에 걸리는 경우 포함)
            out += s.feed(data[i:i + 5])
        self.assertEqual(out, [jpeg(7), jpeg(8)])

    def test_garbage_before_first_frame_is_dropped(self):
        self.assertEqual(FrameSplitter().feed(b"junk\x00\x01" + jpeg(4)), [jpeg(4)])

    def test_incomplete_frame_is_held_until_finished(self):
        s = FrameSplitter()
        self.assertEqual(s.feed(jpeg(5)[:10]), [])
        self.assertEqual(s.feed(jpeg(5)[10:]), [jpeg(5)])


class FrameHubTests(unittest.TestCase):
    def test_latest_and_staleness(self):
        hub = FrameHub()
        self.assertIsNone(hub.latest())
        hub.publish(jpeg(1))
        self.assertEqual(hub.latest(), jpeg(1))
        time.sleep(0.05)
        self.assertIsNone(hub.latest(max_age=0.01))

    def test_wait_next_returns_new_frame_or_times_out(self):
        hub = FrameHub()
        self.assertEqual(hub.wait_next(0, timeout=0.05), (0, None))
        threading.Timer(0.05, hub.publish, args=(jpeg(9),)).start()
        seq, frame = hub.wait_next(0, timeout=2)
        self.assertEqual((seq, frame), (1, jpeg(9)))

    def test_pump_reads_until_stream_closes(self):
        hub = FrameHub()
        pump(io.BytesIO(jpeg(1) + jpeg(2)), hub)
        self.assertEqual(hub.sequence, 2)
        self.assertEqual(hub.latest(), jpeg(2))


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.hub = FrameHub()
        self.server = start_preview_server(self.hub, 0)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_snapshot_is_503_until_a_frame_exists(self):
        self.assertEqual(requests.get(self.base + "/snapshot.jpg", timeout=3).status_code, 503)
        self.hub.publish(jpeg(3))
        r = requests.get(self.base + "/snapshot.jpg", timeout=3)
        self.assertEqual((r.status_code, r.content), (200, jpeg(3)))

    def test_unknown_path_is_404(self):
        self.assertEqual(requests.get(self.base + "/other", timeout=3).status_code, 404)

    def test_stream_pushes_frames_as_they_arrive(self):
        stop = threading.Event()

        def feed():  # 카메라처럼 계속 프레임을 올린다
            n = 0
            while not stop.is_set():
                n += 1
                self.hub.publish(jpeg(n % 200))
                time.sleep(0.03)
        threading.Thread(target=feed, daemon=True).start()
        try:
            with requests.get(self.base + "/stream", stream=True, timeout=5) as r:
                self.assertIn("multipart/x-mixed-replace", r.headers["content-type"])
                data = b""
                for chunk in r.iter_content(4096):
                    data += chunk
                    if data.count(b"--petmindframe") >= 3:
                        break
        finally:
            stop.set()
        self.assertGreaterEqual(data.count(b"Content-Type: image/jpeg"), 3)


if __name__ == "__main__":
    unittest.main()
