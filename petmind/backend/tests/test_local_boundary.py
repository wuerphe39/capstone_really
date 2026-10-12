from fastapi.testclient import TestClient

from .test_flow import client


def test_local_origin_allowed_and_external_origin_rejected(client):
    assert client.get('/health', headers={'Origin': 'http://localhost:8021'}).status_code == 200
    assert client.get('/health', headers={'Origin': 'https://example.org'}).status_code == 403


def test_remote_client_rejected_even_without_origin(client):
    with TestClient(client.app, client=('192.0.2.10', 4444)) as remote:
        assert remote.get('/health').status_code == 403
