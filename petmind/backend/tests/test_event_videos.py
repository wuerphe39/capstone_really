from datetime import datetime, timedelta, timezone
import io
import json

import cv2
import numpy as np
import pytest
import soundfile as sf

from .test_flow import client
from ..database import AudioClipLog, OutingLog, utcnow
from ..routers import audio_clips, outings


@pytest.fixture
def capture_setup(tmp_path,monkeypatch):
    monkeypatch.setattr(audio_clips,'FOLDER',tmp_path/'audio')
    monkeypatch.setattr(audio_clips,'ROOT',tmp_path)
    monkeypatch.setattr(outings,'MEDIA_ROOT',tmp_path/'media')
    checkpoint=tmp_path/'artifacts/audio_lstm/esc50_lstm.pt'
    checkpoint.parent.mkdir(parents=True); checkpoint.touch()
    class Predictor:
        def predict(self,path):
            return {'dog_score':.95,'threshold':.9,'windows':[
                {'start_s':0,'end_s':5,'dog_score':.95,'label':'dog_candidate'}]}
    monkeypatch.setattr('pet_monitor.audio_model_cache.get_audio_predictor',lambda _:Predictor())
    wav=io.BytesIO(); sf.write(wav,np.zeros(80000,dtype=np.float32),16000,format='WAV')
    origin=datetime.now(timezone.utc)-timedelta(minutes=2)
    return wav.getvalue(),origin,tmp_path


def captured(client,setup,offset=5,session='capture-a',outing=None):
    wav,origin,_=setup
    params={'pet_id':'dog','store_consent':True,'captured_at':(origin+timedelta(seconds=offset)).isoformat(),
            'capture_kind':'device','capture_session':session}
    if outing: params['outing_id']=outing
    response=client.post('/audio-clips/upload',params=params,content=wav)
    assert response.status_code==201,response.text
    return response.json()


def movie(setup,duration=15):
    path=setup[2]/'test.mp4'
    writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'mp4v'),10,(64,64))
    assert writer.isOpened()
    for _ in range(duration*10):writer.write(np.zeros((64,64,3),dtype=np.uint8))
    writer.release()
    return path.read_bytes()


def attach(client,setup,ids,offset=0,duration=15,pet='dog'):
    return client.post('/event-videos',params={'pet_id':pet,'clip_ids':ids,'store_consent':True,
        'started_at':(setup[1]+timedelta(seconds=offset)).isoformat()},content=movie(setup,duration))


def test_detection_attach_replay_summary_and_deletion(client,capture_setup):
    outing=client.post('/outings',json={'pet_id':'dog','input_mode':'live'}).json()['id']
    with client.sessions() as db:
        db.get(OutingLog,outing).started_at=capture_setup[1].replace(tzinfo=None)
        db.commit()
    item=captured(client,capture_setup,outing=outing)
    assert item['analysis']['event_video']['status']=='pending'
    response=attach(client,capture_setup,[item['id']]); assert response.status_code==201,response.text
    assert response.json()['status']=='ready'
    # Same upload is idempotent, and no second file is left behind.
    assert attach(client,capture_setup,[item['id']]).status_code==201
    assert len(list(outings.MEDIA_ROOT.glob('*.mp4')))==1
    obs=item['observation_id']; route=f'/outings/observations/{obs}'
    evidence=client.get(route+'/evidence?pet_id=dog').json()
    assert evidence['media_available'] and evidence['event_video']['status']=='ready'
    assert '별도 WAV' not in evidence['note']
    assert client.get(route+'/video?pet_id=other').status_code==404
    player=client.get(route+'/clip?pet_id=dog')
    assert '동일 장치 수집' in player.text and '별도 음원을 결합' not in player.text
    report=client.get(f'/outings/{outing}/summary?pet_id=dog').json()
    assert report['sample_seconds']==5  # never count the 15-second video as analysed audio
    assert report['video_role']=='evidence_only'
    from ..services.outings import summary_facts
    facts=summary_facts(report)
    assert any(f['kind']=='video' and f['observation_ids']==[obs] for f in facts)
    assert '수행하지 않습니다' in next(f['text'] for f in facts if f['id']=='current.unknown')
    assert client.post(f"/audio-clips/{item['id']}/delete-original?pet_id=dog").status_code==200
    assert client.get(route+'/video?pet_id=dog').status_code==410
    assert client.get(route+'/evidence?pet_id=dog').json()['media_available'] is False
    assert list(outings.MEDIA_ROOT.glob('*.mp4'))==[]


def test_partial_merged_event_expiry_and_cross_session(client,capture_setup):
    a=captured(client,capture_setup); b=captured(client,capture_setup,offset=10)
    result=attach(client,capture_setup,[a['id'],b['id']],offset=3,duration=15)
    assert result.status_code==201,result.text
    assert result.json()['status']=='partial'
    assert result.json()['missing_pre_s']==3 and result.json()['missing_post_s']==2
    with client.sessions() as db:
        db.get(AudioClipLog,b['id']).expires_at=utcnow()-timedelta(seconds=1);db.commit()
    assert client.get(f"/outings/observations/{a['observation_id']}/video?pet_id=dog").status_code==410
    client.get('/audio-clips?pet_id=dog')
    assert list(outings.MEDIA_ROOT.glob('*.mp4'))==[]
    c=captured(client,capture_setup,session='different')
    assert attach(client,capture_setup,[a['id'],c['id']]).status_code==422


def test_no_candidate_bad_video_wrong_time_consent_and_missing(client,capture_setup):
    a=captured(client,capture_setup)
    assert attach(client,capture_setup,[a['id']],pet='other').status_code==404
    assert attach(client,capture_setup,[a['id']],offset=40).status_code==422
    assert list(outings.MEDIA_ROOT.glob('*.mp4'))==[]
    params={'pet_id':'dog','clip_ids':[a['id']],'started_at':capture_setup[1].isoformat()}
    assert client.post('/event-videos',params=params,content=b'bad').status_code==422
    assert client.post('/event-videos',params={**params,'store_consent':True},content=b'bad').status_code==422
    missing=client.post('/event-videos/missing',json={'pet_id':'dog','clip_ids':[a['id']],'reason':'buffer_gap'})
    assert missing.status_code==200
    evidence=client.get(f"/outings/observations/{a['observation_id']}/evidence?pet_id=dog").json()
    assert evidence['event_video']['status']=='missing' and evidence['audio_available']
    with client.sessions() as db:
        row=db.get(AudioClipLog,a['id']);data=json.loads(row.analysis_json)
        data['audio_lstm']['windows'][0]['dog_score']=.1;row.analysis_json=json.dumps(data);db.commit()
    assert attach(client,capture_setup,[a['id']]).status_code==422


def test_capture_requires_timezone_and_cannot_be_future(client,capture_setup):
    params={'pet_id':'dog','store_consent':True,'capture_kind':'device','capture_session':'a'}
    for stamp in ['2026-01-01T00:00:00', (datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()]:
        assert client.post('/audio-clips/upload',params={**params,'captured_at':stamp},content=capture_setup[0]).status_code==422


def test_replay_capture_counts_distinct_times_not_identical_silent_bytes(client,capture_setup):
    from ..database import ObservationLog
    from ..services.outings import aggregate
    a=captured(client,capture_setup,offset=5);b=captured(client,capture_setup,offset=10)
    with client.sessions() as db:
        observations=[]
        for item in (a,b):
            audio=db.get(AudioClipLog,item['id']);data=json.loads(audio.analysis_json)
            data['capture']['kind']='file_replay';audio.analysis_json=json.dumps(data)
            obs=db.get(ObservationLog,item['observation_id']);obs.source='user_audio';observations.append(obs)
        db.commit()
        result=aggregate(db,observations)
        assert result['sample_seconds']==10 and result['skipped_overlap_ids']==[]
