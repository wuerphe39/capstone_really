from datetime import datetime, timedelta, timezone

import numpy as np

from .test_flow import client, observe
from petmind.backend.database import AudioClipLog, FeedbackLog
from petmind.backend.services import retrieval
from petmind.backend.services.query_plan import plan_query


def test_kst_day_boundaries_and_explicit_period():
    before = '2026-10-11T02:30:00'
    today = plan_query('오늘 기록', before)
    assert today['start'] == '2026-10-10T15:00:00'
    assert today['before'] == before
    yesterday = plan_query('어제 음악 효과', before)
    assert yesterday['start'] == '2026-10-09T15:00:00'
    assert yesterday['before'] == '2026-10-10T15:00:00'
    assert yesterday['intent'] == 'care_outcome'
    assert plan_query('최근 30일 짖음 빈도', before)['days'] == 30
    assert plan_query('최근 999일', before)['days'] == 90
    night = plan_query('어제 밤 기록', before)
    assert night['start'] == '2026-10-10T09:00:00'
    assert night['before'] == '2026-10-10T15:00:00'


def test_no_irrelevant_recency_citations(client):
    now = datetime.now(timezone.utc)
    observe(client, scenario='calm', when=(now-timedelta(days=1)).isoformat())
    with client.sessions() as db:
        assert retrieval.search_observations(db, 'dog-a', now.isoformat(), '화성 우주선') == []
        result = retrieval.search_result(db, 'dog-a', now.isoformat(), '최근 기록')
        assert result['records'][0]['match_type'] == 'recent_context'
        assert result['search']['recency_context_only'] is True


def test_feedback_is_searchable_and_future_feedback_excluded(client):
    now = datetime.now(timezone.utc)
    record = observe(client, when=(now-timedelta(days=1)).isoformat())
    with client.sessions() as db:
        db.add(FeedbackLog(observation_id=record['id'], feedback_json='{"note":"doorbell"}',
                           created_at=now.replace(tzinfo=None)-timedelta(hours=1)))
        db.add(FeedbackLog(observation_id=record['id'], feedback_json='{"note":"fireworks"}',
                           created_at=now.replace(tzinfo=None)+timedelta(hours=1)))
        db.commit()
        assert retrieval.search_observations(db, 'dog-a', now.isoformat(), 'doorbell')[0]['id'] == record['id']
        assert retrieval.search_observations(db, 'dog-a', now.isoformat(), 'fireworks') == []


def test_audio_review_is_searchable_with_provenance_and_time_scope(client):
    import json
    now = datetime.now(timezone.utc)
    record = observe(client, when=(now-timedelta(days=1)).isoformat())
    with client.sessions() as db:
        row = AudioClipLog(id='review-audio', pet_id='dog-a', observation_id=record['id'],
            filename='unused.wav', sha256='0'*64, duration_s=5, training_consent=0,
            expires_at=now.replace(tzinfo=None)+timedelta(days=6),
            analysis_json=json.dumps({'demo_source':'isolated test'}),
            review_json=json.dumps({'label':'external_or_tv', 'note':'TV로 확인',
                'source':'demo_operator_opinion',
                'updated_at':(now-timedelta(hours=1)).isoformat()}))
        db.add(row); db.commit()
        matched = retrieval.search_result(db, 'dog-a', now.isoformat(), 'TV로 확인')
        assert [r['id'] for r in matched['records']] == [record['id']]
        assert matched['records'][0]['input_scope'] == 'public_demo'
        assert matched['records'][0]['guardian_feedback'][0]['source'] == 'demo_operator_opinion'
        assert retrieval.search_result(db, 'dog-a', (now-timedelta(hours=2)).isoformat(),
            'TV로 확인')['records'] == []
        assert retrieval.search_result(db, 'other-dog', now.isoformat(), 'TV로 확인')['records'] == []


def test_semantics_filtered_before_embedding_and_failures_explicit(client, monkeypatch):
    now = datetime.now(timezone.utc)
    good = observe(client, when=(now-timedelta(days=1)).isoformat())
    observe(client, pet='other-dog', when=(now-timedelta(days=1)).isoformat())
    observe(client, when=(now+timedelta(days=1)).isoformat())
    calls = []
    def embed(texts, task):
        calls.append((texts, task))
        return np.array([[1., 0.]]*len(texts))
    monkeypatch.setattr(retrieval.embeddings, 'embed', embed)
    with client.sessions() as db:
        result = retrieval.search_result(db, 'dog-a', now.isoformat(), 'unusual synonym', semantic=True)
        assert len(calls[0][0]) == 1
        assert [r['id'] for r in result['records']] == [good['id']]
        assert result['search']['method'] == 'hybrid_gemini_embedding_001'
        def fail(*args):
            raise TimeoutError()
        monkeypatch.setattr(retrieval.embeddings, 'embed', fail)
        result = retrieval.search_result(db, 'dog-a', now.isoformat(), 'spinning', semantic=True)
        assert result['search']['method'] == 'lexical_fallback'
        assert result['search']['embedding_failure'] == 'TimeoutError'


def test_same_exact_period_for_search_stats_and_care(client):
    now = datetime.now(timezone.utc)
    observe(client, when=(now-timedelta(days=10)).isoformat())
    recent = observe(client, when=(now-timedelta(days=1)).isoformat())
    with client.sessions() as db:
        start = (now-timedelta(days=2)).isoformat()
        assert retrieval.get_observation_stats(db, 'dog-a', now.isoformat(), 30, start)['sample_count'] == 1
        assert [r['id'] for r in retrieval.search_observations(db, 'dog-a', now.isoformat(), '최근 기록', 30, start=start)] == [recent['id']]
