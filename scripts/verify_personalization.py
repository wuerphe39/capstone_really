"""Same current observation/question, different pet histories, real MCP + Gemini."""
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from petmind.backend.main import analyze_demo
from scripts.verify_flow import request


def main():
    suffix = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc)
    current = analyze_demo('bored_pacing')
    question = ('합성 시연 기록입니다. 현재 짖음 후보의 분당 빈도를 과거 저장 구간과 비교해 '
                '높아졌는지 낮아졌는지 설명하고 근거 기록 ID를 인용해 주세요. 실제 평소 패턴으로 단정하지 마세요.')
    results = []
    for label, past_scenario in [('quiet_history', 'calm'), ('frequent_history', 'anxious')]:
        pet = f'personal-{label}-{suffix}'
        for i in range(2):
            request('POST', '/observations', json={'pet_id': pet, 'session_id': f'past-{i}',
                'observed_at': (now-timedelta(days=i+1)).isoformat(), 'source': 'synthetic_demo',
                'context': analyze_demo(past_scenario)})
        observation = request('POST', '/observations', json={'pet_id': pet, 'session_id': 'identical-current',
            'observed_at': now.isoformat(), 'source': 'synthetic_demo', 'context': current})
        suggestion = request('POST', '/care/evaluate', json={'observation_id': observation['id'], 'question': question})
        assert suggestion['provider'].startswith('gemini:'), suggestion['provider']
        assert suggestion['retrieval']['status'] == 'ok'
        assert all(record['pet_id'] == pet for record in suggestion['retrieval']['records'])
        assert suggestion['cited_observation_ids']
        results.append({'history': label, 'pet_id': pet, 'current': current, 'suggestion': suggestion})
    a, b = results
    assert a['current'] == b['current']
    assert a['suggestion']['question'] == b['suggestion']['question']
    assert a['suggestion']['retrieval']['frequency_comparison']['delta_per_minute'] > 0
    assert b['suggestion']['retrieval']['frequency_comparison']['delta_per_minute'] < 0
    assert not set(a['suggestion']['cited_observation_ids']) & set(b['suggestion']['cited_observation_ids'])
    assert a['suggestion']['summary'] != b['suggestion']['summary']
    report = {'scope': 'two synthetic pet histories; real Gemini/MCP; not a general search quality benchmark', 'results': results}
    for folder in [Path('artifacts'), Path('docs/evidence')]:
        (folder / 'personalization_verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps([{'history': r['history'], 'comparison': r['suggestion']['retrieval']['frequency_comparison'],
                      'summary': r['suggestion']['summary'], 'citations': r['suggestion']['cited_observation_ids']} for r in results], ensure_ascii=False))


if __name__ == '__main__':
    main()
