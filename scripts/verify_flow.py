"""Exercise the running HTTP server and actual virtual agent; save evidence."""
import json
import uuid
from pathlib import Path

import requests

from petmind.device_agent import run_once

BASE = 'http://127.0.0.1:8010'


def request(method, path, **kwargs):
    response = requests.request(method, BASE + path, timeout=30, **kwargs)
    response.raise_for_status()
    return response.json()


def main():
    pet = 'verify-' + uuid.uuid4().hex[:8]
    output = {'pet_id': pet, 'health': request('GET', '/health'), 'scenarios': []}
    request('POST', '/demo/seed', json={'pet_id': pet})
    for scenario in ['calm', 'anxious', 'bored_pacing']:
        obs = request('POST', '/demo/observe', json={'pet_id': pet, 'scenario': scenario})
        suggestion = request('POST', '/care/evaluate', json={'observation_id': obs['id']})
        assert suggestion['retrieval']['status'] == 'ok', suggestion['retrieval']
        assert len(suggestion['retrieval']['tool_calls']) == 3
        action = None
        if suggestion['recommended_actions']:
            action = request('POST', f'/care/{suggestion["id"]}/approve', json={'action_type': 'music'})
            assert action['status'] == 'requested'
            run_once(BASE, Path('device_commands.db'))
            actions = request('GET', f'/care/actions/recent?pet_id={pet}')
            action = next(item for item in actions if item['id'] == action['id'])
            assert action['status'] == 'completed'
        output['scenarios'].append({'scenario': scenario, 'observation': obs, 'suggestion': suggestion, 'action': action})
    output['metrics'] = request('GET', f'/metrics?pet_id={pet}')
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/http_flow.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'pet_id': pet, 'scenarios': 3, 'metrics': output['metrics']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
