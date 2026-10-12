import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from petmind.backend import main, mcp_client
from petmind.backend.database import AudioClipLog, Base, CareActionLog, get_db, utcnow
from petmind.backend.schemas import CareSuggestionDraft, PetContext
from petmind.backend.services import care


@pytest.fixture
def client(tmp_path, monkeypatch):
    url = f'sqlite:///{tmp_path / "test.db"}'
    engine = create_engine(url, connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine)
    def db_override():
        with sessions() as db:
            yield db
    main.app.dependency_overrides[get_db] = db_override
    monkeypatch.setattr(main, 'init_db', lambda: None)
    monkeypatch.setattr(main, 'cleanup_once', lambda: None)
    monkeypatch.setattr(care, 'settings', replace(care.settings, provider='rule', retrieval_mode='local', semantic_enabled=False))
    monkeypatch.setattr(mcp_client, 'settings', replace(mcp_client.settings, database_url=url))
    # Provider selection is independent from the retrieval mode.
    monkeypatch.setattr(care, 'get_provider', lambda: care.RuleBasedProvider())
    with TestClient(main.app) as http:
        http.sessions = sessions
        yield http
    main.app.dependency_overrides.clear()
    engine.dispose()


def observe(client, pet='dog-a', scenario='anxious', when=None):
    payload = {'pet_id': pet, 'session_id': f'{pet}-{when or datetime.now(timezone.utc).isoformat()}',
               'observed_at': when or datetime.now(timezone.utc).isoformat(), 'source': 'synthetic_demo',
               'context': main.analyze_demo(scenario)}
    response = client.post('/observations', json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def evaluate(client, observation):
    response = client.post('/care/evaluate', json={'observation_id': observation['id']})
    assert response.status_code == 200, response.text
    return response.json()


def test_care_uses_current_audio_model_and_review_as_distinct_evidence(client):
    observation = observe(client, scenario='calm')
    with client.sessions() as db:
        db.add(AudioClipLog(id='care-audio', pet_id='dog-a', observation_id=observation['id'],
                            filename='unused.wav', sha256='a'*64, duration_s=5,
                            training_consent=0, expires_at=utcnow()+timedelta(days=1),
                            analysis_json=json.dumps({'input_scope': 'public_demo',
                                'audio_lstm': {'windows': [{'label': 'other_candidate'}],
                                               'dog_score': 0.7, 'threshold': 0.9,
                                               'model_role': 'experimental'}}),
                            review_json=json.dumps({'label': 'uncertain',
                                'source': 'demo_operator_opinion', 'note': 'untrusted text'})))
        db.commit()
    result = evaluate(client, observation)
    current = result['retrieval']['current_audio']
    assert current['observation_id'] == observation['id']
    assert current['input_scope'] == 'public_demo'
    assert (current['analyzed_windows'], current['dog_candidate_windows']) == (1, 0)
    assert (current['review_label'], current['review_source']) == ('uncertain', 'demo_operator_opinion')
    assert 'note' not in current
    assert '개 짖음 소리 후보 0개' in result['reasons'][0]
    assert '시연 담당자 확인 의견: 판단 어려움' in result['reasons'][1]


@pytest.mark.parametrize(('candidates', 'label', 'expected'), [
    (1, 'pet_vocalization', '다음 외출'),
    (0, 'uncertain', '의견을 보완'),
    (0, 'other', '케어 조치를 권하지'),
])
def test_audio_only_care_rule_does_not_invent_an_action(candidates, label, expected):
    context = PetContext(observed_behavior='unknown', behavior_duration_seconds=5,
                         bark_detected=True, bark_count=3, window_s=5)
    evidence = {'current_audio': {'analyzed_windows': 1, 'dog_candidate_windows': candidates,
                                  'review_label': label}, 'records': [], 'status': 'ok', 'stats': {}}
    draft = care.RuleBasedProvider().suggest(context, evidence, '다음에 무엇을 확인할까요?')
    assert expected in draft.summary
    assert draft.recommended_actions == []


def test_care_rejects_model_summary_that_changes_other_sound_review_to_uncertain():
    audio = {'analyzed_windows': 1, 'dog_candidate_windows': 0, 'review_label': 'other'}
    wrong = CareSuggestionDraft(state='insufficient_observation', severity='info',
                                summary='검토 의견이 불확실하므로 원본을 재청취하세요.')
    right = CareSuggestionDraft(state='insufficient_observation', severity='info',
                                summary='기타 소리라는 확인 의견이 있습니다. 케어 조치를 권하지 않습니다.')
    assert care.care_draft_matches_current_audio(wrong, audio) is False
    assert care.care_draft_matches_current_audio(right, audio) is True
    wrong_window_count = CareSuggestionDraft(state='insufficient_observation', severity='info',
        summary='음성 LSTM 창 수는 0개로 측정되어 원본을 다시 들어야 합니다.')
    assert care.care_draft_matches_current_audio(wrong_window_count,
        {**audio, 'review_label': 'uncertain'}) is False


def test_health_reports_audio_checkpoint_presence_without_claiming_validity(client, tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'ROOT', tmp_path)
    monkeypatch.setattr(main, 'SessionLocal', client.sessions)
    key = 'audio_lstm_checkpoint_present'
    assert client.get('/health').json()['components'][key] is False
    checkpoint = tmp_path/'artifacts/audio_lstm/esc50_lstm.pt'
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(b'not a valid model')
    assert client.get('/health').json()['components'][key] is True


def test_observe_evaluate_approve_receive_complete_and_persist(client):
    observation = observe(client)
    suggestion = evaluate(client, observation)
    assert suggestion['status'] == 'pending'
    assert client.get('/care/actions/pending').json() == []
    action = client.post(f'/care/{suggestion["id"]}/approve', json={'action_type': 'music'}).json()
    assert action['status'] == 'requested'
    assert client.post(f'/care/{suggestion["id"]}/approve', json={'action_type': 'music'}).status_code == 409
    path = f'/care/actions/{action["command_id"]}/ack'
    assert client.post(path, json={'status': 'completed'}).status_code == 409
    assert client.post(path, json={'status': 'acknowledged'}).json()['status'] == 'acknowledged'
    assert client.post(path, json={'status': 'completed'}).json()['status'] == 'completed'
    assert client.post(path, json={'status': 'acknowledged'}).status_code == 409
    assert client.post(path, json={'status': 'completed'}).status_code == 200
    with client.sessions() as db:
        assert db.scalars(select(CareActionLog)).one().status == 'completed'
    metrics = client.get('/metrics?pet_id=dog-a').json()
    assert metrics['observations'] == 1 and metrics['actions_completed'] == 1
    assert len(client.get('/timeline?pet_id=dog-a').json()) == 3


def test_search_is_pet_scoped_temporal_and_bounded(client):
    now = datetime.now(timezone.utc)
    past = observe(client, when=(now - timedelta(days=1)).isoformat())
    observe(client, pet='other-dog', when=(now - timedelta(days=1)).isoformat())
    observe(client, when=(now + timedelta(days=1)).isoformat())
    current = observe(client, when=now.isoformat())
    result = evaluate(client, current)
    assert [r['id'] for r in result['retrieval']['records']] == [past['id']]
    assert result['retrieval']['stats']['sample_count'] == 1
    assert result['cited_observation_ids'] == [past['id']]
    assert len(client.get('/observations?pet_id=other-dog').json()) == 1


def test_real_mcp_subprocess_round_trip(client, monkeypatch):
    monkeypatch.setattr(care, 'settings', replace(care.settings, retrieval_mode='mcp'))
    now = datetime.now(timezone.utc)
    past = observe(client, when=(now-timedelta(days=1)).isoformat())
    result = evaluate(client, observe(client, when=now.isoformat()))
    evidence = result['retrieval']
    assert evidence['status'] == 'ok', evidence
    assert evidence['mode'] == 'mcp'
    assert [r['id'] for r in evidence['records']] == [past['id']]
    assert len(evidence['tool_calls']) == 3


def test_timeout_is_terminal(client):
    suggestion = evaluate(client, observe(client))
    action = client.post(f'/care/{suggestion["id"]}/approve', json={}).json()
    with client.sessions() as db:
        row = db.scalars(select(CareActionLog)).one()
        row.created_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)
        db.commit()
    assert client.get('/care/actions/pending').json() == []
    assert client.post(f'/care/actions/{action["command_id"]}/ack', json={'status': 'acknowledged'}).status_code == 409
    assert client.get('/care/actions/recent?pet_id=dog-a').json()[0]['status'] == 'timed_out'


def test_calm_unknown_empty_history_and_dismiss(client):
    result = evaluate(client, observe(client, scenario='calm'))
    assert result['recommended_actions'] == []
    assert result['retrieval']['status'] == 'ok' and result['retrieval']['records'] == []
    assert client.post(f'/care/{result["id"]}/approve', json={}).status_code == 422
    other = evaluate(client, observe(client, pet='new-dog'))
    assert client.post(f'/care/{other["id"]}/dismiss').json()['status'] == 'dismissed'
    assert client.post(f'/care/{other["id"]}/approve', json={}).status_code == 409


def test_audio_only_energy_candidates_do_not_trigger_music():
    context = PetContext(observed_behavior='unknown', behavior_duration_seconds=0,
                         bark_detected=True, bark_count=12, window_s=15,
                         input_note='영상 자동 행동 분석 없음; 음성 관찰')
    draft = care.RuleBasedProvider().suggest(
        context, {'status': 'ok', 'records': [], 'stats': {}}, '현재 상태')
    assert draft.state == 'insufficient_observation'
    assert draft.recommended_actions == []
    assert draft.music_style is None
    assert '소리 원본' in draft.summary


def test_care_steps_follow_human_review_without_inventing_behavior():
    context = PetContext(observed_behavior='unknown', behavior_duration_seconds=0,
                         bark_detected=True, bark_count=9, window_s=15)
    evidence = {'current_audio': {'analyzed_windows': 3, 'dog_candidate_windows': 2,
                                  'review_label': 'external_or_tv'}}
    steps = care.care_steps(context, evidence)
    assert any('TV' in step for step in steps)
    assert not any('음악' in step for step in steps)
    assert not any('9' in step for step in steps)


def test_missing_observation_and_invalid_input(client):
    assert client.post('/care/evaluate', json={'observation_id': 9999}).status_code == 404
    data = observe(client)
    data.pop('id'); data.pop('summary')
    assert data['observed_at'].endswith('Z')
    assert client.post('/observations', json=data).status_code == 409
    data['observed_at'] = '2026-10-11T12:00:00'
    assert client.post('/observations', json=data).status_code == 422
    assert client.get('/observations?pet_id=dog-a&limit=0').status_code == 422


def test_invalid_llm_citation_falls_back(client, monkeypatch):
    class InvalidProvider:
        name = 'gemini:test'
        def suggest(self, context, evidence, question):
            draft = care.RuleBasedProvider().suggest(context, evidence, question)
            draft.cited_observation_ids = [987654]
            return draft
    monkeypatch.setattr(care, 'get_provider', InvalidProvider)
    result = evaluate(client, observe(client))
    assert result['provider'] == 'rule-fallback'
    assert result['cited_observation_ids'] == []


def test_llm_can_cite_the_current_observation_but_not_unrelated_records(client, monkeypatch):
    current = observe(client)
    class CurrentProvider:
        name = 'gemini:test'
        def suggest(self, context, evidence, question):
            assert evidence['current_observation_id'] == current['id']
            draft = care.RuleBasedProvider().suggest(context, evidence, question)
            draft.cited_observation_ids = [current['id']]
            return draft
    monkeypatch.setattr(care, 'get_provider', CurrentProvider)
    result = evaluate(client, current)
    assert result['provider'] == 'gemini:test'
    assert result['cited_observation_ids'] == [current['id']]


def test_mcp_failure_is_not_empty_success(client, monkeypatch):
    async def fail(*args):
        raise RuntimeError('connection failed')
    monkeypatch.setattr(care, 'settings', replace(care.settings, retrieval_mode='mcp'))
    monkeypatch.setattr(care, 'retrieve_records', fail)
    result = evaluate(client, observe(client))
    assert result['retrieval']['status'] == 'failed'
