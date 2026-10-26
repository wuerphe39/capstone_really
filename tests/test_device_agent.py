import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from petmind import device_agent


class Response:
    status_code = 200
    def raise_for_status(self):
        pass
    def json(self):
        return [{'command_id': 'same-command', 'status': 'acknowledged'}]


def test_two_agents_share_one_atomic_cache_claim(tmp_path, monkeypatch):
    cache = tmp_path / 'commands.db'
    with sqlite3.connect(cache) as db:
        db.execute('CREATE TABLE commands (id TEXT PRIMARY KEY, outcome TEXT NOT NULL)')
    barrier = Barrier(2)
    def pending(*args, **kwargs):
        barrier.wait(timeout=5)
        return Response()
    monkeypatch.setattr(device_agent.requests, 'get', pending)
    monkeypatch.setattr(device_agent.requests, 'post', lambda *args, **kwargs: Response())
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(device_agent.run_once, 'http://test', cache, outcome)
                   for outcome in ['completed', 'failed']]
        results = [future.result(timeout=10)[0] for future in futures]
    assert sorted(row['replayed_ack'] for row in results) == [False, True]
    assert results[0]['status'] == results[1]['status']
    with sqlite3.connect(cache) as db:
        assert db.execute('SELECT COUNT(*) FROM commands').fetchone()[0] == 1


def test_retry_uses_saved_result_when_terminal_ack_was_lost(tmp_path, monkeypatch):
    cache = tmp_path / 'commands.db'
    monkeypatch.setattr(device_agent.requests, 'get', lambda *args, **kwargs: Response())
    monkeypatch.setattr(device_agent.requests, 'post', lambda *args, **kwargs: Response())
    first = device_agent.run_once('http://test', cache, 'completed')[0]
    retried = device_agent.run_once('http://test', cache, 'failed')[0]
    assert first['replayed_ack'] is False
    assert retried['replayed_ack'] is True
    assert retried['status'] == first['status'] == 'completed'


def test_isolated_pi_test_does_not_handle_other_commands(tmp_path, monkeypatch):
    monkeypatch.setattr(device_agent.requests, 'get', lambda *args, **kwargs: Response())
    def unexpected_post(*args, **kwargs):
        raise AssertionError('Unselected command must not be acknowledged')
    monkeypatch.setattr(device_agent.requests, 'post', unexpected_post)
    assert device_agent.run_once('http://test', tmp_path/'commands.db', command_id_filter='different-command') == []


class Posts:
    """Records the acknowledgements the agent sends."""
    def __init__(self):
        self.sent = []
    def __call__(self, url, json=None, timeout=None):
        self.sent.append(json)
        return Response()


class Pending:
    status_code = 200
    def raise_for_status(self):
        pass
    def json(self):
        return [{'command_id': 'c1', 'status': 'requested', 'request': {'style': 'calm_piano', 'mode': 'speaker'}}]


class FakePlayer:
    def __init__(self, error=None):
        self.error, self.calls = error, []
    def start(self, style):
        self.calls.append(style)
        if self.error:
            raise self.error
        return f'played {style}'


def run_play(tmp_path, monkeypatch, player, times=1):
    posts = Posts()
    monkeypatch.setattr(device_agent.requests, 'get', lambda *a, **k: Pending())
    monkeypatch.setattr(device_agent.requests, 'post', posts)
    for _ in range(times):
        device_agent.run_once('http://test', tmp_path / 'commands.db', player=player)
    return posts.sent


def test_virtual_agent_still_says_it_played_nothing(tmp_path, monkeypatch):
    sent = run_play(tmp_path, monkeypatch, None)
    assert sent[-1] == {'status': 'completed', 'detail': 'virtual music; no physical playback', 'simulated': True}


def test_playing_agent_reports_a_real_playback(tmp_path, monkeypatch):
    player = FakePlayer()
    sent = run_play(tmp_path, monkeypatch, player)
    assert player.calls == ['calm_piano']
    assert sent[-1] == {'status': 'completed', 'detail': 'played calm_piano', 'simulated': False}


def test_a_retried_command_is_never_played_twice(tmp_path, monkeypatch):
    player = FakePlayer()
    run_play(tmp_path, monkeypatch, player, times=2)
    assert player.calls == ['calm_piano']


def test_a_playback_error_is_reported_as_failed(tmp_path, monkeypatch):
    sent = run_play(tmp_path, monkeypatch, FakePlayer(RuntimeError('no output device')))
    assert sent[-1]['status'] == 'failed' and 'no output device' in sent[-1]['detail'] and sent[-1]['simulated'] is False
