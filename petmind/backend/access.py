"""Who may reach the API.

Default: this PC only (loopback). The prototype has no user accounts, so nothing else is allowed.
LAN mode (PETMIND_LAN_TOKEN set, started with start_demo -Lan): clients on a private network may also connect, but only
with the access key. Public addresses are always refused, even with the key.
"""
import hmac
import ipaddress
import re
import time
from collections import defaultdict
from urllib.parse import parse_qsl, urlencode, urlsplit

COOKIE = 'petmind_key'
MAX_FAILURES = 10          # wrong keys per client and window before that client is locked out
WINDOW_SECONDS = 60.0
COOKIE_MAX_AGE = 30 * 24 * 3600
LOCAL_ORIGIN = re.compile(r'http://(?:localhost|127\.0\.0\.1)(?::\d+)?')
_SHARED_ADDRESS_SPACE = ipaddress.ip_network('100.64.0.0/10')   # carrier NAT / Tailscale
_failures: dict[str, list[float]] = defaultdict(list)


def client_kind(host: str) -> str:
    """'loopback', 'private' (home/office network, link-local, Tailscale range) or 'public'."""
    if host == 'testclient':
        return 'loopback'
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return 'public'
    if ip.is_loopback:
        return 'loopback'
    if ip.is_private or ip.is_link_local or (ip.version == 4 and ip in _SHARED_ADDRESS_SPACE):
        return 'private'
    return 'public'


# A tunnel or reverse proxy running on this PC (Cloudflare Tunnel, ngrok, nginx, tailscale serve ...) reaches the
# backend from 127.0.0.1, so it would look like the PC itself and skip the access key. They announce themselves with
# these headers; such requests are refused. Direct connections (home network, Tailscale address) carry none of them.
PROXY_HEADERS = ('x-forwarded-for', 'x-forwarded-host', 'x-forwarded-proto', 'x-forwarded-port', 'forwarded', 'x-real-ip',
                 'cf-connecting-ip', 'cf-ray', 'cf-visitor', 'true-client-ip', 'x-original-forwarded-for',
                 'tailscale-user-login')


def via_proxy(headers) -> bool:
    return any(name in headers for name in PROXY_HEADERS)


def public_asset(method: str, path: str) -> bool:
    """App name and icons. Browsers fetch the manifest without cookies; none of this is private."""
    if method != 'GET' or '..' in path or '%' in path or chr(92) in path:      # raw clients may send unnormalised paths
        return False
    return path in ('/manifest.json', '/favicon.png') or path.startswith('/icons/')


def key_matches(supplied: str | None, token: str) -> bool:
    return bool(supplied) and bool(token) and hmac.compare_digest(supplied.encode('utf-8'), token.encode('utf-8'))


def same_origin(origin: str, scheme: str, host_header: str) -> bool:
    return origin.rstrip('/').lower() == f'{scheme}://{host_header}'.lower()


def locked_out(host: str, now: float | None = None) -> bool:
    now = time.monotonic() if now is None else now
    recent = [t for t in _failures[host] if now - t < WINDOW_SECONDS]
    _failures[host] = recent
    return len(recent) >= MAX_FAILURES


def record_failure(host: str, now: float | None = None) -> None:
    _failures[host].append(time.monotonic() if now is None else now)


def forget(host: str) -> None:
    _failures.pop(host, None)


def without_key(url: str) -> str:
    """The same URL without the ?key= parameter (so the key does not stay in history or screenshots)."""
    parts = urlsplit(url)
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != 'key'])
    path = parts.path or '/'
    return path + (('?' + query) if query else '')


NEED_KEY_HTML = ('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                 '<title>PetMind</title><body style="font-family:sans-serif;max-width:32em;margin:3em auto;padding:0 1em">'
                 '<h2>접속 키가 필요합니다</h2><p>PetMind를 실행 중인 컴퓨터의 시작 창에 표시된 주소(<code>?key=…</code>가 붙은 주소)로 '
                 '접속해 주세요. 한 번 접속하면 이 기기에서는 키를 다시 입력하지 않아도 됩니다.</p></body>')
