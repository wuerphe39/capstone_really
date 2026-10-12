from datetime import datetime, timedelta, timezone
from .test_flow import client
from ..database import CaptureJob, OutingLog, utcnow
from scripts.pi_outing_agent import clock_healthy


def start(client, **extra):
    return client.post('/outings',json={'pet_id':'auto-dog','input_mode':'live',
        'auto_capture':True,'store_consent':True,**extra})


def agent(**extra):
    return {'pet_id':'auto-dog','owner':'unique-device-owner-1',**extra}


def test_consent_waiting_cancel_and_legacy(client):
    assert start(client,store_consent=False).status_code==422
    assert start(client,input_mode='uploaded_audio').status_code==422
    oid=start(client).json()['id']
    with client.sessions() as db:
        assert db.get(OutingLog, oid).store_consent_at is not None
    assert start(client).status_code==409
    assert client.get(f'/capture/{oid}?pet_id=auto-dog').json()['state']=='waiting'
    assert client.get(f'/capture/{oid}?pet_id=other').status_code==404
    assert client.post(f'/outings/{oid}/end?pet_id=auto-dog').json()['status']=='ended'
    assert client.post('/capture/claim',json=agent()).json()['job'] is None
    assert client.post('/outings',json={'pet_id':'auto-dog','input_mode':'uploaded_audio'}).status_code==201


def test_claim_heartbeat_drain_and_finalize(client):
    oid=start(client).json()['id']
    claimed = client.post('/capture/claim',json=agent()).json()
    assert claimed['job']['outing_id']==oid and claimed['server_time'].endswith('Z')
    assert client.post('/capture/claim',json=agent(owner='second-device-owner')).json()['job'] is None
    route=f'/capture/{oid}/heartbeat'
    assert client.post(route,json=agent(owner='second-device-owner')).status_code==409
    assert client.post(route,json=agent(state='capturing')).json()['state']=='capturing'
    assert client.post(route,json=agent(state='capturing')).json()['server_time'].endswith('Z')
    assert client.post(f'/outings/{oid}/end?pet_id=auto-dog').json()['status']=='active'
    assert client.post(route,json=agent(state='draining')).json()['stop'] is True
    assert client.post(route,json=agent(state='stopped')).status_code==200
    assert client.get(f'/outings/{oid}?pet_id=auto-dog').json()['status']=='ended'
    assert client.post(route,json=agent(state='capturing')).json()['state']=='stopped'
    summary=client.get(f'/outings/{oid}/summary?pet_id=auto-dog').json()
    assert summary['sample_seconds']==0
    assert summary['unobserved_seconds']>0
    explanation=client.post(f'/outings/{oid}/explain',json={
        'pet_id':'auto-dog','question':'이번 외출을 요약해 주세요.'}).json()
    assert '조용했던 시간으로 해석할 수 없습니다' in explanation['answer']


def test_disconnect_not_reclaimed_and_end_marks_failure(client):
    oid=start(client).json()['id']
    client.post('/capture/claim',json=agent())
    with client.sessions() as db:
        db.get(CaptureJob,oid).heartbeat_at=utcnow()-timedelta(seconds=40)
        db.commit()
    assert client.get(f'/capture/{oid}?pet_id=auto-dog').json()['state']=='disconnected'
    assert client.post('/capture/claim',json=agent(owner='another-device-123')).json()['job'] is None
    assert client.post(f'/outings/{oid}/end?pet_id=auto-dog').json()['status']=='ended'
    assert client.post(f'/capture/{oid}/heartbeat',json=agent(state='capturing')).json()['stop'] is True
    assert client.get(f'/capture/{oid}?pet_id=auto-dog').json()['state']=='failed'


def test_clock_skew_stops_before_capture(client):
    oid = start(client).json()['id']
    client.post('/capture/claim', json=agent())
    stamp = datetime(2026, 10, 12, tzinfo=timezone.utc).timestamp()
    assert clock_healthy('2026-10-12T00:00:01Z', stamp + .9, stamp + 1.1)
    assert not clock_healthy('2026-10-12T00:00:05Z', stamp + .9, stamp + 1.1)
    assert not clock_healthy('2026-10-12T00:00:01Z', stamp, stamp + 3)
    route = f'/capture/{oid}/heartbeat'
    assert client.post(route, json=agent(state='clock_mismatch')).json()['state'] == 'clock_mismatch'
    assert client.get(f'/outings/{oid}?pet_id=auto-dog').json()['status'] == 'ended'
