"""Exercise profiles, demo feedback, equal-duration comparison and baseline insufficiency."""
import json
import time
import uuid
from pathlib import Path

from scripts.verify_flow import request, BASE
from petmind.device_agent import run_once


def main():
    pet = 'extras-verify-' + uuid.uuid4().hex[:8]
    profile = request('POST', f'/pets/{pet}/profile', json={'name': '가상 시연 반려견', 'age_years': 3,
                       'living_pattern': '합성 시연용 생활 패턴', 'guardian_note': '실제 반려견 프로필이 아닌 검증용 자료'})
    observation = request('POST', '/demo/observe', json={'pet_id': pet, 'scenario': 'anxious'})
    suggestion = request('POST', '/care/evaluate', json={'observation_id': observation['id']})
    assert suggestion['retrieval']['profile']['pet_id'] == pet
    feedback = request('POST', '/feedback', json={'observation_id': observation['id'], 'suggestion_id': suggestion['id'],
                       'suggestion_appropriate': True, 'source': 'synthetic_demo', 'note': '합성 시연용 의견; 실제 보호자 평가가 아님'})
    assert feedback['source'] == 'synthetic_demo'
    action = request('POST', f'/care/{suggestion["id"]}/approve', json={})
    run_once(BASE, Path('device_commands.db'))
    print('Waiting for an equal-duration 30-second post-action demo window...', flush=True)
    time.sleep(31)
    after = request('POST', '/demo/observe', json={'pet_id': pet, 'scenario': 'calm'})
    comparison = request('GET', f'/care/actions/{action["command_id"]}/comparison')
    assert comparison['status'] == 'ok' and comparison['causality_established'] is False
    baseline = request('GET', f'/pets/{pet}/baseline?observation_id={after["id"]}')
    assert baseline['status'] == 'insufficient_data'
    report = {'pet_id': pet, 'profile': profile, 'feedback': feedback, 'comparison': comparison, 'baseline': baseline}
    Path('artifacts/extras_verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'profile_saved': True, 'feedback_source': feedback['source'],
                      'comparison': comparison['status'], 'baseline': baseline['status']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
