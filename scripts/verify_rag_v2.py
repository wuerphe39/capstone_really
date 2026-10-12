"""Real embedding + official MCP + Gemini integration with isolated test pet IDs."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests


def run():
    base = 'http://127.0.0.1:8010'
    pet = 'rag-v2-' + datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    def post(path, payload):
        response = requests.post(base+path, json=payload, timeout=60)
        response.raise_for_status(); return response.json()
    old = post('/demo/observe', {'pet_id': pet, 'scenario': 'bored_pacing'})
    post('/feedback', {'observation_id': old['id'], 'note': '현관 초인종이 울린 직후 왕복 이동을 관찰했습니다.'})
    current = post('/demo/observe', {'pet_id': pet, 'scenario': 'anxious'})
    result = post('/care/evaluate', {'observation_id': current['id'],
                                    'question': '오늘 문 앞에서 벨 소리가 났을 때 반응과 지금을 비교해줘'})
    assert result['retrieval']['status'] == 'ok', result['retrieval']
    assert result['retrieval']['search']['method'] == 'hybrid_gemini_embedding_001', result['retrieval']['search']
    assert [r['id'] for r in result['retrieval']['records']] == [old['id']]
    assert result['provider'].startswith('gemini:'), result['provider']
    assert set(result['cited_observation_ids']).issubset({old['id']})
    assert current['context']['lstm_metadata']['feature_version'] == 2
    Path('artifacts/rag/real_integration.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'provider': result['provider'], 'search': result['retrieval']['search']['method'],
                      'period': result['retrieval']['query_plan']['period'],
                      'retrieved': [r['id'] for r in result['retrieval']['records']],
                      'citations': result['cited_observation_ids'], 'lstm_feature_version': 2}), flush=True)


if __name__ == '__main__':
    run()
