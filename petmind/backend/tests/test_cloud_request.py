import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from .test_flow import client, observe  # noqa: F401 - fixture
from .. import providers
from ..services import care


class GeminiReply:
    def raise_for_status(self):
        pass

    def json(self):
        draft = {'state': 'insufficient_observation', 'summary': '기록이 적습니다.', 'reasons': ['근거 부족'], 'recommended_actions': [],
                 'music_style': None, 'severity': 'info', 'cited_observation_ids': []}
        return {'candidates': [{'content': {'parts': [{'text': json.dumps(draft, ensure_ascii=False)}]}}]}


@pytest.fixture
def cloud(client, monkeypatch):  # noqa: F811
    posted = {}

    def post(url, headers=None, json=None, timeout=None):
        posted.update(url=url, headers=headers, body=json)
        return GeminiReply()
    monkeypatch.setattr(providers, 'settings', replace(providers.settings, provider='gemini', gemini_api_key='secret-test-key'))
    monkeypatch.setattr(providers.requests, 'post', post)
    monkeypatch.setattr(care, 'get_provider', providers.GeminiProvider)
    client.posted = posted
    return client


def history(client, count=3):
    """Earlier observations of the same dog, so that retrieval has something to find."""
    now = datetime.now(timezone.utc)
    for i in range(count):
        observe(client, when=(now - timedelta(days=1, minutes=i)).isoformat())


def evaluate(client, question='최근 기록과 비교해서 어떤 케어가 필요할까요?'):
    observation = observe(client, when=datetime.now(timezone.utc).isoformat())
    return client.post('/care/evaluate', json={'observation_id': observation['id'], 'question': question}).json()


def test_rules_are_the_system_instruction_and_the_data_is_the_user_message(cloud):
    history(cloud)
    evaluate(cloud)
    body = cloud.posted['body']
    assert body['systemInstruction']['parts'][0]['text'].startswith('반려견 관찰을 한국어로 설명하는 케어 보조 시스템입니다')
    (message,) = body['contents']
    assert message['role'] == 'user'
    data = json.loads(message['parts'][0]['text'].split('\n', 1)[1])
    assert set(data) == {'question', 'context', 'evidence'} and data['question'].startswith('최근 기록과 비교')
    assert data['evidence']['records'], 'the retrieved records must be part of what is sent'
    assert '반려견 관찰을 한국어로' not in message['parts'][0]['text']  # rules are not repeated in the user message


def test_the_secret_stays_in_the_header_and_never_in_the_body(cloud):
    evaluate(cloud)
    assert cloud.posted['headers']['x-goog-api-key'] == 'secret-test-key'
    assert 'secret-test-key' not in json.dumps(cloud.posted['body'], ensure_ascii=False)


def test_the_suggestion_records_exactly_what_was_sent(cloud):
    history(cloud)
    suggestion = evaluate(cloud)
    record = suggestion['retrieval']['cloud_request']
    assert record['sent'] is True and record['used_in_answer'] is True and record['host'] == 'generativelanguage.googleapis.com'
    assert record['system_instruction'] == cloud.posted['body']['systemInstruction']['parts'][0]['text']
    assert record['user_message'] == cloud.posted['body']['contents'][0]['parts'][0]['text']
    sent_ids = json.loads(record['user_message'].split('\n', 1)[1])['evidence']['records']
    assert record['record_ids'] == [r['id'] for r in sent_ids] and record['record_ids']
    assert '원본 음원·영상' in record['not_sent']
    assert 'secret-test-key' not in json.dumps(suggestion, ensure_ascii=False)


def test_the_rule_provider_sends_nothing_and_says_so(client, monkeypatch):  # noqa: F811
    suggestion = client.post('/care/evaluate', json={'observation_id': observe(client)['id'], 'question': '상태가 어때?'}).json()
    record = suggestion['retrieval']['cloud_request']
    assert record['sent'] is False and '클라우드로 보낸 것이 없습니다' in record['reason']
