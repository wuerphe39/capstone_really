import io
import threading
import time
from picamera2 import Picamera2
from picamera2.encoders import MJPEGEncoder
from picamera2.outputs import FileOutput


class StreamOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = threading.Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()


class Camera:
    WIDTH = 1920
    HEIGHT = 1080
    FPS = 30

    def __init__(self):
        self.picam = Picamera2()
        config = self.picam.create_video_configuration(
            main={"size": (self.WIDTH, self.HEIGHT), "format": "RGB888"},
            controls={"FrameRate": self.FPS},
        )
        self.picam.configure(config)
        self.output = StreamOutput()
        self._running = False

    def start(self):
        self.picam.start_recording(MJPEGEncoder(), FileOutput(self.output))
        self._running = True

    def stop(self):
        self.picam.stop_recording()
        self._running = False

    def capture_frame(self):
        return self.picam.capture_array()

    def get_mjpeg_frame(self) -> bytes:
        with self.output.condition:
            self.output.condition.wait()
            return self.output.frame

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.stop()
