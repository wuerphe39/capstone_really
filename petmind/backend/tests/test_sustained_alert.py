import io
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
import requests
import soundfile as sf

from .test_flow import client  # noqa: F401 - fixture
from ..database import OutingLog, utcnow
from ..routers import audio_clips
from ..services import alerts

T0 = datetime(2026, 10, 26, 8, 0, 0)


def item(i, candidate, window=5.0, gap=0.0):
    return {'observed_at': T0 + timedelta(seconds=i * (window + gap)), 'window_s': window, 'candidate': candidate}


def newest_first(flags, **kwargs):
    return list(reversed([item(i, c, **kwargs) for i, c in enumerate(flags)]))


def test_six_windows_of_candidates_in_a_row_are_sustained():
    found = alerts.find_sustained(newest_first([True] * 6))
    assert found == {'seconds': 30.0, 'windows': 6, 'candidate_windows': 6}


def test_one_quiet_window_inside_the_stretch_is_tolerated():
    assert alerts.find_sustained(newest_first([True, True, False, True, True, True]))['candidate_windows'] == 5


def test_two_quiet_windows_are_not_sustained():
    assert alerts.find_sustained(newest_first([True, False, True, False, True, True])) is None


def test_barking_that_has_already_stopped_is_not_an_alert():
    assert alerts.find_sustained(newest_first([True] * 5 + [False])) is None


def test_less_than_thirty_seconds_is_not_sustained():
    assert alerts.find_sustained(newest_first([True] * 5)) is None


def test_a_hole_between_recordings_breaks_the_stretch():
    assert alerts.find_sustained(newest_first([True] * 6, gap=20.0)) is None


def wav():
    output = io.BytesIO()
    sf.write(output, np.zeros(5 * 16000, dtype=np.float32), 16000, format='WAV')
    return output.getvalue()


@pytest.fixture
def live(client, monkeypatch, tmp_path):  # noqa: F811
    monkeypatch.setattr(audio_clips, 'FOLDER', tmp_path / 'audio')
    monkeypatch.setattr(audio_clips, 'settings', replace(audio_clips.settings, audio_detector='yamnet', yamnet_url='http://127.0.0.1:8030/analyze'))
    scores = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {'model': 'YAMNet Bark (direct score; no LSTM)', 'threshold': .05,
                    'windows': [{'start_s': 0, 'end_s': 5, 'bark_score': scores.pop(0), 'padded': False}]}
    monkeypatch.setattr(audio_clips.requests, 'post', lambda *args, **kwargs: Response())
    monkeypatch.setattr(alerts, 'DELIVER_IN_BACKGROUND', False)
    outing = client.post('/outings', json={'pet_id': 'dog-a', 'input_mode': 'live', 'title': '지속 짖음 시험',
                                          'auto_capture': True, 'store_consent': True}).json()['id']
    start = datetime.now(timezone.utc) - timedelta(seconds=60)
    with client.sessions() as db:  # the outing began before the recordings the test sends
        row = db.get(OutingLog, outing)
        row.started_at = utcnow() - timedelta(minutes=5)
        db.commit()

    def record(score, index):
        scores.append(score)
        when = (start + timedelta(seconds=5 * index)).isoformat()
        response = client.post(f'/audio-clips/upload?pet_id=dog-a&store_consent=true&outing_id={outing}&capture_kind=device'
                               f'&capture_session=s1&captured_at={when.replace("+", "%2B")}', content=wav(), headers={'Content-Type': 'audio/wav'})
        assert response.status_code == 201, response.text
    client.record, client.outing = record, outing
    return client


def test_sustained_barking_creates_a_pending_music_offer_and_one_alert(live, monkeypatch):
    sent = []
    monkeypatch.setattr(alerts, 'settings', replace(alerts.settings, ntfy_topic='petmind-test-topic-0123456789', ntfy_server='https://ntfy.example',
                                                    public_url='http://100.64.0.1:8010/'))
    monkeypatch.setattr(alerts, 'http_post', lambda url, json, timeout: sent.append((url, json)) or type('R', (), {'raise_for_status': lambda self: None})())
    for i in range(5):
        live.record(.8, i)
    assert live.get('/care/alerts?pet_id=dog-a').json() == []
    live.record(.8, 5)
    found = live.get('/care/alerts?pet_id=dog-a').json()
    assert len(found) == 1 and found[0]['notify_status'] == 'sent' and found[0]['window_seconds'] == 30
    suggestion = live.get('/care/latest?pet_id=dog-a').json()
    assert suggestion['provider'] == 'sustained-bark-rule' and suggestion['status'] == 'pending'
    assert suggestion['recommended_actions'] == ['music'] and '아무 소리도 재생되지 않습니다' in suggestion['summary']
    (url, message), = sent
    assert url == 'https://ntfy.example' and message['topic'] == 'petmind-test-topic-0123456789'
    assert message['click'] == 'http://100.64.0.1:8010/'
    assert set(message) == {'topic', 'title', 'message', 'priority', 'tags', 'click'}  # a sentence and a link, nothing recorded
    live.record(.8, 6)  # still barking: no second alert inside the cool-down
    assert len(live.get('/care/alerts?pet_id=dog-a').json()) == 1
    assert live.post(f"/care/{suggestion['id']}/approve", json={'action_type': 'music'}).status_code == 200  # approval still required and works


def test_without_a_topic_the_alert_is_in_the_app_only(live, monkeypatch):
    monkeypatch.setattr(alerts, 'settings', replace(alerts.settings, ntfy_topic=''))
    monkeypatch.setattr(alerts, 'http_post', lambda *a, **k: pytest.fail('nothing may be sent without a topic'))
    for i in range(6):
        live.record(.8, i)
    assert live.get('/care/alerts?pet_id=dog-a').json()[0]['notify_status'] == 'not_configured'


def test_a_failed_notification_is_recorded_and_the_alert_remains(live, monkeypatch):
    monkeypatch.setattr(alerts, 'settings', replace(alerts.settings, ntfy_topic='petmind-test-topic-0123456789'))

    def boom(*a, **k):
        raise requests.ConnectionError()
    monkeypatch.setattr(alerts, 'http_post', boom)
    for i in range(6):
        live.record(.8, i)
    row = live.get('/care/alerts?pet_id=dog-a').json()[0]
    assert row['notify_status'] == 'failed'


def test_quiet_recordings_never_alert(live):
    for i in range(8):
        live.record(.01, i)
    assert live.get('/care/alerts?pet_id=dog-a').json() == []
