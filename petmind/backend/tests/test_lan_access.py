from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from .. import access, main

TOKEN = 'k3y-for-tests-0123456789abcd'
LAN_IP = ('192.168.1.20', 50000)


@pytest.fixture(autouse=True)
def fresh_failures():
    access._failures.clear()
    yield
    access._failures.clear()


@pytest.fixture
def lan_mode(monkeypatch, tmp_path):
    web = tmp_path / 'web'
    (web / 'assets').mkdir(parents=True)
    (web / 'index.html').write_text('<html>app shell</html>', encoding='utf-8')
    (web / 'main.js').write_text('console.log(1)', encoding='utf-8')
    (tmp_path / 'secret.txt').write_text('outside the web folder', encoding='utf-8')
    monkeypatch.setattr(main, 'settings', replace(main.settings, lan_token=TOKEN, web_dir=web))
    return web


def lan_client(host=LAN_IP, **kwargs):
    return TestClient(main.app, client=host, follow_redirects=False, **kwargs)


def test_without_lan_mode_a_private_client_is_refused_like_before(monkeypatch):
    monkeypatch.setattr(main, 'settings', replace(main.settings, lan_token='', web_dir=None))
    response = lan_client().get('/openapi.json', headers={'x-petmind-key': TOKEN})
    assert response.status_code == 403


def test_this_pc_keeps_working_and_foreign_web_origins_stay_refused(lan_mode):
    local = TestClient(main.app)
    assert local.get('/openapi.json').status_code == 200
    assert local.get('/openapi.json', headers={'origin': 'http://localhost:8021'}).status_code == 200
    assert local.get('/openapi.json', headers={'origin': 'http://evil.example'}).status_code == 403


def test_private_client_needs_the_key_and_gets_a_cookie_once(lan_mode):
    client = lan_client()
    assert client.get('/openapi.json').status_code == 401
    page = client.get('/', headers={'accept': 'text/html'})
    assert page.status_code == 401 and '접속 키' in page.text
    first = client.get('/openapi.json?key=' + TOKEN)
    assert first.status_code == 303
    assert first.headers['location'] == '/openapi.json'            # the key is not left in the address bar
    cookie = first.headers['set-cookie']
    assert access.COOKIE in cookie and 'httponly' in cookie.lower() and 'samesite=lax' in cookie.lower()
    again = lan_client(cookies={access.COOKIE: TOKEN})
    assert again.get('/openapi.json').status_code == 200
    assert lan_client().get('/openapi.json', headers={'x-petmind-key': TOKEN}).status_code == 200


def test_wrong_key_is_refused_and_a_post_cannot_use_the_query_key(lan_mode):
    client = lan_client()
    assert client.get('/openapi.json?key=nope').status_code == 401
    assert client.post('/outings?key=' + TOKEN, json={}).status_code == 401
    assert client.get('/openapi.json', headers={'x-petmind-key': 'x' * len(TOKEN)}).status_code == 401


@pytest.mark.parametrize('header', ['x-forwarded-for', 'cf-connecting-ip', 'cf-ray', 'x-real-ip', 'forwarded', 'x-forwarded-host'])
def test_a_tunnel_on_this_pc_cannot_pass_as_this_pc(lan_mode, header):
    # Cloudflare Tunnel, ngrok and reverse proxies connect from 127.0.0.1 and add these headers.
    local = TestClient(main.app)
    assert local.get('/openapi.json').status_code == 200
    assert local.get('/openapi.json', headers={header: '203.0.113.9'}).status_code == 403
    assert local.get('/openapi.json', headers={header: '203.0.113.9', 'x-petmind-key': TOKEN}).status_code == 403   # the key does not help


def test_a_tunnel_is_refused_without_lan_mode_too(monkeypatch):
    monkeypatch.setattr(main, 'settings', replace(main.settings, lan_token='', web_dir=None))
    assert TestClient(main.app).get('/openapi.json', headers={'x-forwarded-for': '203.0.113.9'}).status_code == 403


def test_private_clients_behind_no_proxy_are_unaffected(lan_mode):
    assert lan_client(cookies={access.COOKIE: TOKEN}).get('/openapi.json').status_code == 200


def test_app_name_and_icons_are_public_to_the_private_network_but_nothing_else(lan_mode):
    client = lan_client()
    for path in ('/manifest.json', '/favicon.png', '/icons/Icon-192.png'):
        assert client.get(path).status_code in (200, 404)          # reaches the web folder (these files are absent in the test folder)
    assert client.get('/main.js').status_code == 401               # the app itself still needs the key
    assert client.get('/icons/../main.js').status_code == 401
    assert client.post('/manifest.json').status_code == 401         # only reading is public
    assert lan_client(('8.8.8.8', 1)).get('/manifest.json').status_code == 403   # and only inside the private network


def test_public_asset_rule_rejects_tricks_a_raw_client_could_send():
    assert access.public_asset('GET', '/icons/Icon-192.png') and access.public_asset('GET', '/manifest.json')
    for path in ('/icons/../main.js', '/icons/%2e%2e/main.js', '/icons/..%5cmain.js', '/main.js', '/manifest.json/../main.js'):
        assert not access.public_asset('GET', path), path
    assert not access.public_asset('POST', '/manifest.json')


def test_public_addresses_are_refused_even_with_the_key(lan_mode):
    response = lan_client(('8.8.8.8', 4000)).get('/openapi.json', headers={'x-petmind-key': TOKEN})
    assert response.status_code == 403


def test_a_valid_cookie_does_not_help_a_request_from_another_site(lan_mode):
    client = lan_client(cookies={access.COOKIE: TOKEN})
    assert client.get('/openapi.json', headers={'origin': 'http://evil.example'}).status_code == 403
    assert client.get('/openapi.json', headers={'origin': 'http://testserver'}).status_code == 200  # same origin


def test_repeated_wrong_keys_lock_the_client_out(lan_mode):
    client = lan_client()
    for _ in range(access.MAX_FAILURES):
        assert client.get('/openapi.json?key=wrong').status_code == 401
    assert client.get('/openapi.json?key=' + TOKEN).status_code == 429
    assert lan_client(('192.168.1.99', 1)).get('/openapi.json?key=' + TOKEN).status_code == 303   # other clients unaffected


def test_the_web_app_is_served_to_keyed_clients_and_api_routes_win(lan_mode):
    client = lan_client(cookies={access.COOKIE: TOKEN})
    assert 'app shell' in client.get('/').text
    assert client.get('/main.js').text == 'console.log(1)'
    assert 'app shell' in client.get('/some/screen').text            # client-side route falls back to the shell
    assert client.get('/missing.js').status_code == 404              # a missing asset is not the app shell
    assert client.get('/openapi.json').json()['info']['title'] == 'PetMind integrated API'
    assert client.get('/%2e%2e/secret.txt').status_code == 404       # cannot leave the web folder


def test_nothing_is_served_at_the_root_without_a_web_folder(monkeypatch):
    monkeypatch.setattr(main, 'settings', replace(main.settings, lan_token='', web_dir=None))
    assert TestClient(main.app).get('/').status_code == 404


@pytest.mark.parametrize('host,kind', [
    ('127.0.0.1', 'loopback'), ('::1', 'loopback'), ('testclient', 'loopback'),
    ('192.168.0.7', 'private'), ('10.1.2.3', 'private'), ('172.20.64.159', 'private'), ('169.254.3.4', 'private'),
    ('100.101.102.103', 'private'), ('8.8.8.8', 'public'), ('172.32.0.1', 'public'), ('not-an-ip', 'public'),
])
def test_client_kind(host, kind):
    assert access.client_kind(host) == kind


def test_key_is_removed_from_the_redirect_target_but_other_parameters_stay():
    assert access.without_key('http://pc:8010/?key=abc&pet_id=dog-a') == '/?pet_id=dog-a'
    assert access.without_key('http://pc:8010/outings?key=abc') == '/outings'
    assert access.key_matches('abc', 'abc') and not access.key_matches('abd', 'abc') and not access.key_matches(None, 'abc')
