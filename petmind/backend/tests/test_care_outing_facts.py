import io
from dataclasses import replace

import numpy as np
import pytest
import soundfile as sf

from .test_flow import client  # noqa: F401 - fixture
from ..routers import audio_clips


def wav():
    output = io.BytesIO()
    sf.write(output, np.zeros(16000, dtype=np.float32), 16000, format='WAV')
    return output.getvalue()


@pytest.fixture
def fixture(client, monkeypatch, tmp_path):  # noqa: F811
    monkeypatch.setattr(audio_clips, 'FOLDER', tmp_path / 'audio')
    monkeypatch.setattr(audio_clips, 'settings', replace(audio_clips.settings, audio_detector='yamnet', yamnet_url='http://127.0.0.1:8030/analyze'))

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {'model': 'YAMNet Bark (direct score; no LSTM)', 'threshold': .05,
                    'windows': [{'start_s': 0, 'end_s': 1, 'bark_score': .8, 'padded': True}]}
    monkeypatch.setattr(audio_clips.requests, 'post', lambda *args, **kwargs: Response())
    return client


def upload(client, outing):
    response = client.post(f'/audio-clips/upload?pet_id=dog-a&store_consent=true&outing_id={outing}', content=wav(),
                           headers={'Content-Type': 'audio/wav'})
    assert response.status_code == 201, response.text
    return response.json()


def test_a_guardian_review_of_an_earlier_recording_reaches_the_care_evaluation(fixture):
    first = fixture.post('/outings', json={'pet_id': 'dog-a', 'input_mode': 'uploaded_audio'}).json()['id']
    clip = upload(fixture, first)
    assert fixture.post(f"/audio-clips/{clip['id']}/review",
                        json={'pet_id': 'dog-a', 'label': 'external_or_tv', 'note': '검증용: TV 소리로 확인'}).status_code == 200
    fixture.post(f'/outings/{first}/end', params={'pet_id': 'dog-a'})
    second = fixture.post('/outings', json={'pet_id': 'dog-a', 'input_mode': 'uploaded_audio'}).json()['id']
    current = upload(fixture, second)['observation_id']
    suggestion = fixture.post('/care/evaluate', json={'observation_id': current, 'question': '보호자가 TV라고 확인한 기록이 있어?'}).json()
    facts = suggestion['retrieval']['outing_facts']
    earlier = [f for f in facts if f['id'].startswith('previous.')]
    assert earlier and 'TV' in earlier[0]['text'] and clip['observation_id'] in earlier[0]['observation_ids']
    assert {'tool': 'get_outing_facts', 'status': 'local'} in suggestion['retrieval']['tool_calls']


def test_an_observation_outside_any_outing_just_has_no_outing_facts(client):  # noqa: F811
    from .test_flow import observe
    suggestion = client.post('/care/evaluate', json={'observation_id': observe(client)['id'], 'question': '상태가 어때?'}).json()
    assert suggestion['retrieval']['outing_facts'] == []


def test_an_earlier_outing_is_always_reported_as_comparable_or_why_not(fixture):
    first = fixture.post('/outings', json={'pet_id': 'dog-a', 'input_mode': 'uploaded_audio'}).json()['id']
    earlier = upload(fixture, first)['observation_id']
    fixture.post(f'/outings/{first}/end', params={'pet_id': 'dog-a'})
    second = fixture.post('/outings', json={'pet_id': 'dog-a', 'input_mode': 'uploaded_audio'}).json()['id']
    current = upload(fixture, second)['observation_id']
    suggestion = fixture.post('/care/evaluate', json={'observation_id': current, 'question': '지난번과 비교해서 어떤 케어가 필요할까요?'}).json()
    fact = next(f for f in suggestion['retrieval']['outing_facts'] if f['id'].startswith('comparison.'))
    assert fact['id'] == 'comparison.model_windows' and '이전 외출은 분석 창 1개 중 1개' in fact['text']
    assert earlier in fact['observation_ids'] and current in fact['observation_ids']
    assert '평소 패턴과 비교한 것이 아니며' in fact['text']


def explain(client, outing, question):
    return client.post(f'/outings/{outing}/explain', json={'pet_id': 'dog-a', 'question': question}).json()


def test_asking_about_a_guardian_confirmation_that_does_not_exist_says_so(fixture):
    outing = fixture.post('/outings', json={'pet_id': 'dog-a', 'input_mode': 'uploaded_audio'}).json()['id']
    upload(fixture, outing)
    answer = explain(fixture, outing, '보호자가 TV라고 확인한 기록이 있어?')['answer']
    assert '보호자가 남긴 확인 의견이 없습니다' in answer
    assert '음성 관찰' not in answer  # no filler lines that look like an answer


def test_a_confirmation_that_exists_is_still_found(fixture):
    outing = fixture.post('/outings', json={'pet_id': 'dog-a', 'input_mode': 'uploaded_audio'}).json()['id']
    clip = upload(fixture, outing)
    fixture.post(f"/audio-clips/{clip['id']}/review", json={'pet_id': 'dog-a', 'label': 'external_or_tv', 'note': '검증용: TV 소리로 확인'})
    answer = explain(fixture, outing, '보호자가 TV라고 확인한 기록이 있어?')['answer']
    assert 'TV' in answer and '확인 의견이 없습니다' not in answer


def test_health_and_emotion_questions_get_a_clear_refusal_and_other_questions_the_plain_default(fixture):
    outing = fixture.post('/outings', json={'pet_id': 'dog-a', 'input_mode': 'uploaded_audio'}).json()['id']
    upload(fixture, outing)
    assert '건강 상태나 감정을 판단하지 않습니다' in explain(fixture, outing, '우리 강아지가 아픈 거야?')['answer']
    assert explain(fixture, outing, '내일 날씨는?')['answer'] == '질문을 뒷받침할 외출 기록이 부족합니다.'
