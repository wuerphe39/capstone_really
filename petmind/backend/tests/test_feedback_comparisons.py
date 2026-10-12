from datetime import datetime, timedelta, timezone

from .test_flow import client, observe, evaluate
from petmind.backend.main import analyze_demo


def test_feedback_matches_observation_and_pet(client):
    observation = observe(client)
    suggestion = evaluate(client, observation)
    feedback = client.post('/feedback', json={'observation_id': observation['id'], 'suggestion_id': suggestion['id'],
                                             'bark_present': False, 'suggestion_appropriate': True, 'note': '검토할 시연 의견'})
    assert feedback.status_code == 201
    assert feedback.json()['source'] == 'guardian_feedback'
    assert client.get('/feedback?pet_id=dog-a').json()[0]['bark_present'] is False
    assert client.get('/feedback?pet_id=other-dog').json() == []
    other = observe(client, pet='other-dog')
    assert client.post('/feedback', json={'observation_id': other['id'], 'suggestion_id': suggestion['id'], 'note': '잘못된 연결'}).status_code == 422
    assert client.post('/feedback', json={'observation_id': observation['id']}).status_code == 422


def test_guardian_feedback_is_available_as_retrieval_evidence(client):
    now = datetime.now(timezone.utc)
    past = observe(client, when=(now-timedelta(days=1)).isoformat())
    client.post('/feedback', json={'observation_id': past['id'], 'bark_present': False})
    current = observe(client, when=(now+timedelta(seconds=1)).isoformat())
    result = evaluate(client, current)
    assert result['retrieval']['records'][0]['guardian_feedback'][0]['bark_present'] is False


def test_before_after_comparison_requires_completed_equal_windows(client):
    observation = observe(client)
    suggestion = evaluate(client, observation)
    action = client.post(f'/care/{suggestion["id"]}/approve', json={}).json()
    path = f'/care/actions/{action["command_id"]}'
    assert client.get(path+'/comparison').json()['status'] == 'insufficient_data'
    client.post(path+'/ack', json={'status': 'acknowledged'})
    completed = client.post(path+'/ack', json={'status': 'completed'}).json()
    assert client.get(path+'/comparison').json()['status'] == 'insufficient_data'
    when = datetime.fromisoformat(completed['updated_at'].replace('Z', '+00:00')) + timedelta(seconds=31)
    after = observe(client, scenario='calm', when=when.isoformat())
    result = client.get(path+'/comparison').json()
    assert result['status'] == 'ok'
    assert result['after_observation_id'] == after['id']
    assert result['candidate_count_delta'] < 0
    assert result['scope'] == 'demo_windows' and result['causality_established'] is False


def test_baseline_rejects_demo_and_requires_multiple_live_days(client):
    current = observe(client)
    assert client.get(f'/pets/dog-a/baseline?observation_id={current["id"]}').json()['status'] == 'insufficient_data'
    assert client.get(f'/pets/other-dog/baseline?observation_id={current["id"]}').status_code == 404
    now = datetime(2026, 10, 11, 3, 30, tzinfo=timezone.utc)
    def live(when, scenario='calm'):
        response = client.post('/observations', json={'pet_id': 'baseline-dog', 'session_id': when.isoformat(),
            'observed_at': when.isoformat(), 'source': 'live', 'context': analyze_demo(scenario)})
        assert response.status_code == 201, response.text
        return response.json()
    observation = live(now)
    path = f'/pets/baseline-dog/baseline?observation_id={observation["id"]}'
    assert client.get(path).json()['status'] == 'insufficient_data'
    for i in range(10):
        live(now-timedelta(days=1+i//3, seconds=i%3))
    result = client.get(path).json()
    assert result['status'] == 'ok' and result['sample_count'] == 10
    assert result['distinct_days'] >= 3
