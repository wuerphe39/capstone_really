import pytest
import requests
from .test_flow import client
from ..routers import camera


def test_camera_unconfigured_and_player(client, monkeypatch):
    monkeypatch.delenv('PETMIND_CAMERA_SNAPSHOT_URL', raising=False)
    assert client.get('/camera/snapshot').status_code == 503
    response = client.get('/camera/view')
    assert response.status_code == 200
    assert '카메라 보기 시작' in response.text
    assert "/camera/stream" in response.text and 'setTimeout' not in response.text  # pushed stream, no polling
    assert response.headers['cache-control'] == 'no-store'


@pytest.mark.parametrize('payload,status', [(b'\xff\xd8test\xff\xd9', 200),
    (b'not a jpeg', 503), (b'\xff\xd8'+b'x'*(camera.MAX_FRAME)+b'\xff\xd9', 503)], ids=['jpeg', 'invalid', 'oversized'])
def test_camera_frame_validation(client, monkeypatch, payload, status):
    monkeypatch.setenv('PETMIND_CAMERA_SNAPSHOT_URL', 'http://127.0.0.1:18081/snapshot.jpg')
    class Upstream:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_content(self, size): yield payload
    def get(url, **kwargs):
        assert url == 'http://127.0.0.1:18081/snapshot.jpg'
        assert kwargs['allow_redirects'] is False
        return Upstream()
    monkeypatch.setattr(camera.requests, 'get', get)
    response = client.get('/camera/snapshot')
    assert response.status_code == status
    if status == 200:
        assert response.content == payload
        assert response.headers['cache-control'] == 'no-store'


def test_camera_disconnection(client, monkeypatch):
    monkeypatch.setenv('PETMIND_CAMERA_SNAPSHOT_URL', 'http://127.0.0.1:18081/snapshot.jpg')
    def fail(*args, **kwargs): raise requests.ConnectionError('private host detail')
    monkeypatch.setattr(camera.requests, 'get', fail)
    response = client.get('/camera/snapshot')
    assert response.status_code == 503
    assert 'private host detail' not in response.text


def test_stream_unconfigured_is_503(client, monkeypatch):
    monkeypatch.delenv('PETMIND_CAMERA_SNAPSHOT_URL', raising=False)
    assert client.get('/camera/stream').status_code == 503


class StreamUpstream:
    def __init__(self, status=200, content_type='multipart/x-mixed-replace; boundary=petmindframe', parts=(b'--petmindframe\r\nA', b'B')):
        self.status_code, self.headers, self.parts, self.closed = status, {'content-type': content_type}, parts, False
    def iter_content(self, size):
        yield from self.parts
    def close(self):
        self.closed = True


def test_stream_relays_the_multipart_body_and_closes_upstream(client, monkeypatch):
    monkeypatch.setenv('PETMIND_CAMERA_SNAPSHOT_URL', 'http://127.0.0.1:18081/snapshot.jpg')
    up = StreamUpstream()
    def get(url, **kwargs):
        assert url == 'http://127.0.0.1:18081/stream'
        assert kwargs['stream'] is True and kwargs['allow_redirects'] is False
        return up
    monkeypatch.setattr(camera.requests, 'get', get)
    response = client.get('/camera/stream')
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('multipart/x-mixed-replace')
    assert response.headers['cache-control'] == 'no-store'
    assert response.content == b'--petmindframe\r\nAB'
    assert up.closed


@pytest.mark.parametrize('upstream', [StreamUpstream(status=503), StreamUpstream(content_type='text/html')], ids=['status', 'content-type'])
def test_stream_rejects_a_bad_upstream_and_closes_it(client, monkeypatch, upstream):
    monkeypatch.setenv('PETMIND_CAMERA_SNAPSHOT_URL', 'http://127.0.0.1:18081/snapshot.jpg')
    monkeypatch.setattr(camera.requests, 'get', lambda *a, **k: upstream)
    assert client.get('/camera/stream').status_code == 503
    assert upstream.closed


def test_stream_disconnection_hides_host_details(client, monkeypatch):
    monkeypatch.setenv('PETMIND_CAMERA_SNAPSHOT_URL', 'http://127.0.0.1:18081/snapshot.jpg')
    def fail(*args, **kwargs): raise requests.ConnectionError('private host detail')
    monkeypatch.setattr(camera.requests, 'get', fail)
    response = client.get('/camera/stream')
    assert response.status_code == 503 and 'private host detail' not in response.text


# ---- remote viewers get small frames pulled one at a time (no backlog on slow mobile connections) -------------------
from dataclasses import replace

from fastapi.testclient import TestClient

from .. import access, main

TOKEN = 'k3y-for-camera-tests-0123456'


def noisy_jpeg(width=640, height=480, quality=90):
    cv2 = pytest.importorskip('cv2')
    np = pytest.importorskip('numpy')
    image = np.random.default_rng(1).integers(0, 255, (height, width, 3), dtype=np.uint8)
    ok, out = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    assert ok
    return out.tobytes()


def serve_frame(monkeypatch, payload):
    class Upstream:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_content(self, size): yield payload
    monkeypatch.setenv('PETMIND_CAMERA_SNAPSHOT_URL', 'http://127.0.0.1:18081/snapshot.jpg')
    monkeypatch.setattr(camera.requests, 'get', lambda *a, **k: Upstream())


def remote(monkeypatch):
    monkeypatch.setattr(main, 'settings', replace(main.settings, lan_token=TOKEN))
    return TestClient(main.app, client=('192.168.1.20', 50000), cookies={access.COOKIE: TOKEN})


def test_this_pc_gets_the_continuous_stream_page_and_a_remote_viewer_the_low_bandwidth_page(client, monkeypatch):
    local = client.get('/camera/view').text
    assert "frame.src='/camera/stream?'" in local and '/camera/snapshot?width=' not in local
    phone = remote(monkeypatch).get('/camera/view').text
    assert '/camera/snapshot?width=' in phone and "'/camera/stream?'" not in phone
    assert 'mode=' not in phone                      # nothing to switch to: the continuous stream is not offered remotely


def test_this_pc_can_choose_the_view_but_a_remote_viewer_cannot_ask_for_the_continuous_stream(client, monkeypatch):
    assert '/camera/snapshot?width=' in client.get('/camera/view?mode=poll').text
    assert 'mode=push' in client.get('/camera/view?mode=poll').text         # this PC may switch back
    phone = remote(monkeypatch).get('/camera/view?mode=push').text          # asking for it from outside is ignored
    assert '/camera/snapshot?width=' in phone and "'/camera/stream?'" not in phone and 'mode=' not in phone
    assert client.get('/camera/view?mode=bogus').status_code == 422


def test_snapshot_can_be_scaled_down_and_never_up(client, monkeypatch):
    cv2 = pytest.importorskip('cv2')
    np = pytest.importorskip('numpy')
    original = noisy_jpeg()
    serve_frame(monkeypatch, original)
    small = client.get('/camera/snapshot?width=240&quality=40')
    assert small.status_code == 200 and small.headers['content-type'] == 'image/jpeg'
    decoded = cv2.imdecode(np.frombuffer(small.content, np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape[1] == 240 and decoded.shape[0] == 180        # aspect ratio kept
    assert len(small.content) < len(original) / 4
    assert client.get('/camera/snapshot').content == original          # no width: untouched
    assert client.get('/camera/snapshot?width=1280').content == original   # never enlarged


def test_snapshot_size_limits_are_validated(client, monkeypatch):
    serve_frame(monkeypatch, b'\xff\xd8test\xff\xd9')
    assert client.get('/camera/snapshot?width=50').status_code == 422
    assert client.get('/camera/snapshot?width=240&quality=5').status_code == 422
    assert client.get('/camera/snapshot?width=240&quality=99').status_code == 422
