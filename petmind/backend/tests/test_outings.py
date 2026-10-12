import hashlib
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from .test_flow import client
from ..database import AudioClipLog, ObservationLog, ObservationMedia, OutingLog
from ..services import outings
from ..routers import outings as routes


@pytest.fixture(autouse=True)
def local_explanation(monkeypatch):
    monkeypatch.setattr(outings, 'settings', replace(outings.settings, provider='rule', retrieval_mode='local'))


def start(client, pet='dog-a', mode='synthetic_demo'):
    response = client.post('/outings', json={'pet_id': pet, 'input_mode': mode})
    assert response.status_code == 201, response.text
    return response.json()['id']


def observe(client, outing, pet='dog-a'):
    response = client.post('/demo/observe', json={'pet_id': pet, 'scenario': 'anxious', 'outing_id': outing})
    assert response.status_code == 201, response.text
    return response.json()


def test_lifecycle_legacy_and_isolation(client):
    oid = start(client)
    assert client.post('/outings', json={'pet_id': 'dog-a'}).status_code == 409
    observation = observe(client, oid)
    assert observation['outing_id'] == oid
    assert client.get('/observations?pet_id=dog-a').json()[0]['outing_id'] == oid
    assert client.get(f'/outings/{oid}/summary?pet_id=other').status_code == 404
    assert client.post(f'/outings/{oid}/end?pet_id=other').status_code == 404
    assert client.post('/demo/observe', json={'pet_id': 'other', 'outing_id': oid}).status_code == 404
    report = client.get(f'/outings/{oid}/summary?pet_id=dog-a').json()
    assert report['sample_seconds'] > 0
    assert sum(report['seconds_by_label'].values()) == pytest.approx(report['sample_seconds'])
    assert report['moments'][0]['media_available'] is False
    assert report['unobserved_seconds'] is None
    first = client.post(f'/outings/{oid}/end?pet_id=dog-a').json()
    assert client.post(f'/outings/{oid}/end?pet_id=dog-a').json() == first
    assert client.post('/demo/observe', json={'pet_id': 'dog-a', 'outing_id': oid}).status_code == 409
    assert start(client) != oid
    assert client.post('/demo/observe', json={'pet_id': 'legacy'}).json()['outing_id'] is None


def test_energy_candidates_and_lstm_windows_are_separate_metrics(client):
    oid = start(client)
    observation = observe(client, oid)
    with client.sessions() as db:
        row = db.get(ObservationLog, observation['id'])
        duration = json.loads(row.context_json)['window_s']
        db.add(AudioClipLog(id='metric-audio', pet_id='dog-a', observation_id=row.id,
            filename='missing.wav', sha256='a'*64, duration_s=duration,
            training_consent=0, expires_at=datetime.now(timezone.utc).replace(tzinfo=None)+timedelta(days=7),
            analysis_json=json.dumps({'audio_lstm': {'threshold': .7, 'windows': [
                {'start_s': 0, 'end_s': 1, 'dog_score': .8},
                {'start_s': 1, 'end_s': 2, 'dog_score': .2}]}})))
        db.commit()
    report = client.get(f'/outings/{oid}/summary?pet_id=dog-a').json()
    assert report['energy_bark_candidate_count'] == report['bark_candidate_count']
    assert report['lstm_analyzed_window_count'] == 2
    assert report['lstm_dog_window_count'] == 1
    assert report['lstm_unavailable_seconds'] == 0
    claims = client.post(f'/outings/{oid}/explain', json={'pet_id': 'dog-a'}).json()['claims']
    assert not any(c['id'] == 'current.bark' for c in claims)
    assert any(c['id'] == 'current.audio_lstm' and '1개' in c['text'] for c in claims)
    assert '소리 크기 변화' not in report['moments'][0]['summary']
    assert '개 짖음 소리 후보 1개' in report['moments'][0]['summary']
    model_claims = client.post(f'/outings/{oid}/explain', json={
        'pet_id': 'dog-a', 'question': 'LSTM 개 소리 후보 창은 몇 개야?'}).json()['claims']
    assert any(c['id'] == 'current.audio_lstm' and '1개' in c['text'] for c in model_claims)


def test_old_cited_observation_evidence_can_be_opened_across_outings(client, tmp_path, monkeypatch):
    monkeypatch.setattr(routes, 'MEDIA_ROOT', tmp_path)
    first = start(client)
    past = observe(client, first)
    assert client.post(f'/outings/{first}/end?pet_id=dog-a').status_code == 200
    second = start(client)
    observe(client, second)
    assert past['id'] not in client.get(f'/outings/{second}/summary?pet_id=dog-a').json()['counted_observation_ids']
    content = b'public-video-test'
    (tmp_path/'past.mp4').write_bytes(content)
    with client.sessions() as db:
        db.add(ObservationMedia(observation_id=past['id'], filename='past.mp4',
            sha256=hashlib.sha256(content).hexdigest(), start_s=0, end_s=10,
            source_json=json.dumps({'attribution': 'test', 'license': 'test'})))
        db.commit()

    response = client.get(f'/outings/observations/{past["id"]}/evidence?pet_id=dog-a')
    assert response.status_code == 200
    evidence = response.json()
    assert evidence['observation_id'] == past['id']
    assert evidence['media_available'] is True
    assert evidence['clip_url'] == f'/outings/observations/{past["id"]}/clip?pet_id='
    assert client.get(f'/outings/observations/{past["id"]}/evidence?pet_id=other').status_code == 404
    assert client.get('/outings/observations/999999/evidence?pet_id=dog-a').status_code == 404


def test_source_time_and_empty_evidence(client):
    oid = start(client, mode='prepared_video')
    assert client.post('/demo/observe', json={'pet_id': 'dog-a', 'outing_id': oid}).status_code == 422
    result = client.post(f'/outings/{oid}/explain', json={'pet_id': 'dog-a'}).json()
    assert result['claims'] == [] and result['report']['sample_seconds'] == 0
    old = observe(client, None, pet='legacy')
    oid2 = start(client, pet='legacy')
    old.pop('id'); old.pop('summary'); old['outing_id'] = oid2
    assert client.post('/observations', json=old).status_code == 422


@pytest.mark.parametrize('question', [
    '녹음이 총 몇 분이나 쌓였나요?',
    '얼마나 오래 봤는지 알려줘',
])
def test_natural_duration_questions_retrieve_measured_sample_time(client, question):
    oid = start(client)
    observe(client, oid)
    result = client.post(f'/outings/{oid}/explain', json={
        'pet_id': 'dog-a', 'question': question}).json()
    assert any(c['kind'] == 'summary' and '초' in c['text'] for c in result['claims'])


def test_duplicate_video_unknown_and_media_integrity(client, tmp_path, monkeypatch):
    monkeypatch.setattr(routes, 'MEDIA_ROOT', tmp_path)
    oid = start(client)
    one, two = observe(client, oid), observe(client, oid)
    content = b'0123456789'
    (tmp_path / 'sample.mp4').write_bytes(content)
    with client.sessions() as db:
        for item in (one, two):
            row = db.get(ObservationLog, item['id'])
            context = json.loads(row.context_json)
            context['motion']['seconds_by_label'] = {'moving': 3}
            row.context_json = json.dumps(context)
            db.add(ObservationMedia(observation_id=row.id, filename='sample.mp4',
                sha256=hashlib.sha256(content).hexdigest(), start_s=0, end_s=context['window_s'],
                source_json=json.dumps({'attribution': '<script>bad()</script>', 'license': 'test'})))
        db.commit()
    report = client.get(f'/outings/{oid}/summary?pet_id=dog-a').json()
    assert report['counted_observation_ids'] == [one['id']]
    assert report['skipped_overlap_ids'] == [two['id']]
    assert report['unknown_seconds'] == report['sample_seconds'] - 3
    path = f"/outings/observations/{one['id']}"
    assert client.get(path+'/clip?pet_id=dog-a').status_code == 200
    assert '<script>bad()' not in client.get(path+'/clip?pet_id=dog-a').text
    assert client.get(path+'/video?pet_id=other').status_code == 404
    part = client.get(path+'/video?pet_id=dog-a', headers={'Range': 'bytes=2-5'})
    assert part.status_code == 206 and part.content == b'2345'
    (tmp_path / 'sample.mp4').write_bytes(b'changed')
    assert client.get(path+'/video?pet_id=dog-a').status_code == 409
    (tmp_path / 'sample.mp4').unlink()
    assert client.get(path+'/clip?pet_id=dog-a').status_code == 404
    missing = client.get(f'/outings/{oid}/summary?pet_id=dog-a').json()['moments'][0]
    assert missing['media_available'] is False and missing['clip_url'] is None
    assert '원본 파일이 없습니다' in missing['note']


def test_kst_day_and_live_boundary(client):
    one, two = observe(client, None), observe(client, None)
    with client.sessions() as db:
        a, b = db.get(ObservationLog, one['id']), db.get(ObservationLog, two['id'])
        a.observed_at = datetime(2026, 10, 10, 15, 0, 10)  # crosses KST midnight
        b.observed_at = datetime(2026, 10, 10, 15, 2)
        a.source = b.source = 'live'
        db.commit()
    report = client.get('/outings/day?pet_id=dog-a&day=2026-10-11').json()
    assert report['timezone'] == 'Asia/Seoul'
    assert report['excluded_day_boundary_ids'] == [one['id']]
    assert report['counted_observation_ids'] == [two['id']]
    assert client.get('/outings/day?pet_id=dog-a&day=2026-10-10').json()['sample_seconds'] == 0
    explanation = client.post('/outings/day/explain?day=2026-10-11', json={
        'pet_id': 'dog-a', 'question': '오늘 요약과 판단 불가 시간'}).json()
    assert explanation['report']['counted_observation_ids'] == [two['id']]
    assert explanation['retrieval_mode'] == 'local-day'
    assert all(c['observation_ids'] == [two['id']] for c in explanation['claims'])
    assert str(report['bark_candidate_count']) in next(c['text'] for c in explanation['claims'] if c['kind'] == 'bark')
    assert client.post('/outings/day/explain?day=2026-10-11', json={
        'pet_id': 'other', 'question': '오늘 요약'}).json()['claims'] == []


def test_comparison_scoped_and_no_unsupported_question(client):
    previous = start(client)
    old = observe(client, previous)
    client.post(f'/outings/{previous}/end?pet_id=dog-a')
    other = start(client, pet='other')
    distractor = observe(client, other, pet='other')
    current = start(client)
    now = observe(client, current)
    result = client.post(f'/outings/{current}/explain', json={'pet_id': 'dog-a', 'question': '지난 외출과 비교'}).json()
    comparison = next(c for c in result['claims'] if c['id'] == 'comparison.bark_rate')
    assert set(comparison['observation_ids']) == {old['id'], now['id']}
    assert distractor['id'] not in comparison['observation_ids']
    assert client.post(f'/outings/{current}/explain', json={'pet_id': 'dog-a', 'question': '내일 날씨는?'}).json()['claims'] == []


def test_prior_tv_review_cited_without_current_pet_sound_confusion(client):
    first = start(client)
    old = observe(client, first)
    client.post(f'/outings/{first}/end?pet_id=dog-a')
    second = start(client)
    now = observe(client, second)
    with client.sessions() as db:
        for index, observation, label in ((1, old, 'external_or_tv'),
                                          (2, now, 'pet_vocalization')):
            db.add(AudioClipLog(id=f'rag-audio-{index}', pet_id='dog-a',
                observation_id=observation['id'], filename='unused.wav',
                sha256=str(index)*64, duration_s=30, training_consent=0,
                expires_at=datetime.now(timezone.utc).replace(tzinfo=None)+timedelta(days=7),
                analysis_json='{}', review_json=json.dumps({'label':label,
                    'source':'guardian_opinion','note':'isolated test'})))
        db.commit()
    result=client.post(f'/outings/{second}/explain',json={'pet_id':'dog-a',
        'question':'보호자가 TV라고 확인한 것은?'}).json()
    assert [c['observation_ids'] for c in result['claims']] == [[old['id']]]
    assert 'TV·외부 소리' in result['answer']
    assert now['id'] not in {i for c in result['claims'] for i in c['observation_ids']}
    fullwidth=client.post(f'/outings/{second}/explain',json={'pet_id':'dog-a',
        'question':'보호자가 ＴＶ 소리라고 확인한 것은?'}).json()
    assert [c['observation_ids'] for c in fullwidth['claims']] == [[old['id']]]


def test_mcp_outing_roundtrip_and_invalid_generated_fact(client, monkeypatch):
    oid = start(client)
    observe(client, oid)
    monkeypatch.setattr(outings, 'settings', replace(outings.settings, retrieval_mode='mcp'))
    result = client.post(f'/outings/{oid}/explain', json={'pet_id': 'dog-a'}).json()
    assert result['retrieval_mode'] == 'mcp', result
    assert result['claims'] and result['retrieval_failure'] is None
    monkeypatch.setattr(outings, 'settings', replace(outings.settings, provider='gemini', gemini_api_key='test', retrieval_mode='local'))
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {'candidates': [{'content': {'parts': [{'text': '{"fact_ids":["invented"]}'}]}}]}
    monkeypatch.setattr('requests.post', lambda *a, **k: Response())
    result = client.post(f'/outings/{oid}/explain', json={'pet_id': 'dog-a'}).json()
    assert result['provider'] == 'grounded-template-fallback'
    assert result['failure'] == 'ValueError'
    assert all(c['id'] in result['retrieved_fact_ids'] for c in result['claims'])


@pytest.mark.parametrize(('review_label', 'detected', 'expected'), [
    ('pet_vocalization', True, '다음 외출'),
    ('pet_vocalization', False, '놓친 사례'),
    ('uncertain', False, '불확실'),
    ('other', False, '케어 조치를 권하지'),
])
def test_next_check_uses_only_selected_current_evidence(review_label, detected, expected):
    report = {'lstm_analyzed_window_count': 1,
              'lstm_dog_window_count': int(detected),
              'moments': [{'observation_id': 7, 'included_in_metrics': True,
                           'guardian_review': {'label': review_label}}]}
    claims = [{'id': 'current.audio_lstm', 'observation_ids': [7]},
              {'id': 'guardian.7', 'observation_ids': [7]}]
    suggestions = outings.next_check_suggestions(report, claims)
    assert len(suggestions) == 1
    assert expected in suggestions[0]['text']
    assert suggestions[0]['observation_ids'] == [7]
    assert suggestions[0]['basis_fact_ids'] == ['current.audio_lstm', 'guardian.7']
    assert outings.next_check_suggestions(report, claims[:1])[0]['basis_fact_ids'] == ['current.audio_lstm']
    assert outings.next_check_suggestions(report, claims[1:]) == []
    assert outings.next_check_suggestions(report, [{'id': 'current.audio_lstm', 'observation_ids': [99]}]) == []


def test_visitor_scene_note_is_retrieved_as_demo_description_not_detection(client):
    oid = start(client)
    observation = observe(client, oid)
    with client.sessions() as db:
        row = db.get(ObservationLog, observation['id'])
        duration = json.loads(row.context_json)['window_s']
        db.add(AudioClipLog(id='visitor-demo', pet_id='dog-a', observation_id=row.id,
            filename='unused.wav', sha256='b'*64, duration_s=duration, training_consent=0,
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None)+timedelta(days=1),
            analysis_json=json.dumps({'demo_source': '집에 초인종 소리가 나고 노크 소리가 들린 뒤 개가 짖는 소리가 들립니다.',
                'audio_lstm': {'threshold': 0.9, 'windows': [
                    {'start_s': 0, 'end_s': 5, 'dog_score': 0.06, 'label': 'other_candidate'},
                    {'start_s': 5, 'end_s': 10, 'dog_score': 0.96, 'label': 'dog_candidate'}]}}),
            review_json='{}'))
        db.commit()
    result = client.post(f'/outings/{oid}/explain', json={'pet_id': 'dog-a',
        'question': '초인종과 노크 뒤 개 짖음 소리 후보가 있었나요? 방문 사실은 확인됐나요?'}).json()
    scene = next(fact for fact in result['claims'] if fact['id'] == f"scene.{observation['id']}")
    assert '업로드 담당자 입력 설명' in scene['text']
    assert '실제 방문 사실이 아닙니다' in scene['text']
    assert scene['observation_ids'] == [observation['id']]
    assert '현관 영상·방문 기록' in result['next_steps'][0]['text']
    assert result['next_steps'][0]['basis_fact_ids'] == [f"scene.{observation['id']}", 'current.audio_lstm']
