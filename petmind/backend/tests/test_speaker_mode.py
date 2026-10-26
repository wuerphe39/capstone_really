from dataclasses import replace

from .test_flow import client, evaluate, observe  # noqa: F401 - fixture
from ..services import care
from .. import main


def approved_action(client):
    suggestion = evaluate(client, observe(client))
    return client.post(f'/care/{suggestion["id"]}/approve', json={'action_type': 'music'}).json()


def finish(client, action, **ack):
    path = f'/care/actions/{action["command_id"]}/ack'
    assert client.post(path, json={'status': 'acknowledged'}).status_code == 200
    return client.post(path, json={'status': 'completed', **ack}).json()


def test_by_default_the_music_is_virtual(client):
    assert client.get('/health').json()['components']['action_mode'] == 'simulated'
    action = approved_action(client)
    assert action['request']['mode'] == 'simulated'
    assert finish(client, action, detail='virtual')['result']['simulated'] is True


def test_a_speaker_agent_records_that_it_really_played(client, monkeypatch):
    monkeypatch.setattr(care, 'settings', replace(care.settings, action_mode='speaker'))
    monkeypatch.setattr(main, 'settings', replace(main.settings, action_mode='speaker'))
    assert client.get('/health').json()['components']['action_mode'] == 'speaker'
    action = approved_action(client)
    assert action['request']['mode'] == 'speaker'
    result = finish(client, action, detail='PC 스피커로 재생 시작', simulated=False)['result']
    assert result == {'simulated': False, 'detail': 'PC 스피커로 재생 시작'}
