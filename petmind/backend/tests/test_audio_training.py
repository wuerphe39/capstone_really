import json
from datetime import timedelta

import pytest

from .test_flow import client
from .test_audio_clips import isolated_audio, upload
from ..database import AudioClipLog, utcnow
from ..services.audio_training import build_manifest, resolve_manifest, verify
from ..services.audio_retention import cleanup_once


def reviewed(client, training=True):
    item = upload(client,'&training_consent='+str(training).lower())
    client.post('/audio-clips/'+item['id']+'/review',json={'pet_id':'dog-a','label':'other','note':'test fixture'})
    return item


def test_no_consent_no_export_and_independent_review_required(client):
    item = reviewed(client,False)
    with client.sessions() as db:
        with pytest.raises(ValueError,match='no_training_consent'):
            verify(db,item['id'],'other','tester','synthetic silence fixture')
        assert build_manifest(db)['records'] == []
    client.post('/audio-clips/'+item['id']+'/consent',json={'pet_id':'dog-a','training_consent':True})
    with client.sessions() as db:
        assert build_manifest(db)['records'] == []
        verify(db,item['id'],'other','tester','synthetic silence fixture')
        manifest = build_manifest(db)
        assert len(manifest['records']) == 1
        assert len(resolve_manifest(db,manifest)) == 1


@pytest.mark.parametrize('change',['withdraw','opinion','expire','delete','tamper'])
def test_export_becomes_invalid_after_material_change(client,change):
    item = reviewed(client)
    with client.sessions() as db:
        verify(db,item['id'],'other','tester','synthetic silence fixture')
        manifest = build_manifest(db)
    prefix = '/audio-clips/'+item['id']
    if change == 'withdraw':
        client.post(prefix+'/consent',json={'pet_id':'dog-a','training_consent':False})
    elif change == 'opinion':
        client.post(prefix+'/review',json={'pet_id':'dog-a','label':'uncertain'})
    elif change == 'delete':
        client.post(prefix+'/delete-original?pet_id=dog-a')
    else:
        with client.sessions() as db:
            row = db.get(AudioClipLog,item['id'])
            if change == 'expire': row.expires_at = utcnow()-timedelta(seconds=1)
            else:
                from ..routers.audio_clips import path_for
                path_for(row).write_bytes(b'changed')
            db.commit()
    with client.sessions() as db:
        with pytest.raises(ValueError,match='stale or revoked'):
            resolve_manifest(db,manifest)


def test_duplicate_audio_and_conflicting_labels_are_excluded(client):
    a,b = reviewed(client),reviewed(client)
    with client.sessions() as db:
        verify(db,a['id'],'other','tester','silence')
        verify(db,b['id'],'other','tester','silence')
        assert len(build_manifest(db)['records']) == 1
        verify(db,b['id'],'dog','tester','intentional conflicting test label')
        assert build_manifest(db)['records'] == []


def test_queue_includes_routine_negative_and_excludes_reviewed(client):
    a,b,c = upload(client),upload(client),upload(client)
    with client.sessions() as db:
        for index,item in enumerate((a,b,c)):
            row = db.get(AudioClipLog,item['id'])
            data = json.loads(row.analysis_json)
            data.update(dog_score=.01 if index == 2 else .89,model_disagreement=False,
                        audio_lstm={'threshold':.9})
            row.analysis_json = json.dumps(data)
        db.commit()
    result = client.get('/audio-clips/review-queue?pet_id=dog-a&limit=2').json()
    assert {x['review_priority'] for x in result['items']} == {'uncertain','routine_sample'}
    client.post('/audio-clips/'+c['id']+'/review',json={'pet_id':'dog-a','label':'other'})
    assert c['id'] not in {x['id'] for x in client.get('/audio-clips/review-queue?pet_id=dog-a').json()['items']}
    assert client.get('/audio-clips/review-queue?pet_id=other').json()['items'] == []


def test_background_cleanup_does_not_need_a_user_request(client):
    item = reviewed(client)
    with client.sessions() as db:
        row = db.get(AudioClipLog,item['id'])
        row.expires_at = utcnow()-timedelta(seconds=1)
        db.commit()
    cleanup_once(client.sessions)
    with client.sessions() as db:
        row = db.get(AudioClipLog,item['id'])
        assert row.deleted_at is not None and not row.training_consent
        from ..routers.audio_clips import path_for
        assert not path_for(row).exists()
