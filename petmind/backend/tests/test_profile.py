from .test_flow import client, observe, evaluate


def test_profile_is_saved_and_scoped_for_evaluation(client):
    result = client.post('/pets/dog-a/profile', json={'name': '테스트 반려견', 'age_years': 3,
                                                    'living_pattern': '오후 산책', 'guardian_note': '시연용 메모'})
    assert result.status_code == 200
    assert result.json()['source'] == 'guardian_input'
    assert client.get('/pets/other-dog/profile').json() is None
    assert evaluate(client, observe(client))['retrieval']['profile']['name'] == '테스트 반려견'
    assert evaluate(client, observe(client, pet='other-dog'))['retrieval']['profile'] is None


def test_profile_update_and_validation(client):
    assert client.post('/pets/dog-a/profile', json={'name': '', 'age_years': -1}).status_code == 422
    client.post('/pets/dog-a/profile', json={'name': '첫 이름'})
    client.post('/pets/dog-a/profile', json={'name': '수정 이름', 'age_years': None})
    assert client.get('/pets/dog-a/profile').json()['name'] == '수정 이름'
