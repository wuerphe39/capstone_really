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
    assert "clearFrame();state.textContent=err.message" in response.text
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
