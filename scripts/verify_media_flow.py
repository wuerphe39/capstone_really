import json
import uuid
from pathlib import Path

from scripts.verify_flow import request, BASE
from petmind.device_agent import run_once


def main():
    evaluation = json.loads(Path('artifacts/audio_evaluation.json').read_text(encoding='utf-8'))
    clip = max((r for r in evaluation['records'] if r['expected_dog_clip']), key=lambda r: r['candidate_count'])
    pet = 'public-verify-' + uuid.uuid4().hex[:8]
    request('POST', '/demo/seed', json={'pet_id': pet})
    media = request('POST', '/media/observe', json={'pet_id': pet, 'audio_filename': clip['filename'], 'include_video': True})
    suggestion = request('POST', '/care/evaluate', json={'observation_id': media['observation']['id']})
    assert media['observation']['context']['motion_model'] == 'lstm_synthetic'
    assert suggestion['retrieval']['status'] == 'ok' and len(suggestion['retrieval']['tool_calls']) == 3
    action = None
    if suggestion['recommended_actions']:
        action = request('POST', f'/care/{suggestion["id"]}/approve', json={})
        run_once(BASE, Path('device_commands.db'))
        action = next(item for item in request('GET', f'/care/actions/recent?pet_id={pet}') if item['id'] == action['id'])
        assert action['status'] == 'completed'
    output = {'pet_id': pet, 'media': media, 'suggestion': suggestion, 'action': action}
    Path('artifacts/public_http_flow.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'pet_id': pet, 'audio_file': clip['filename'], 'bark_candidates': clip['candidate_count'],
                      'provider': suggestion['provider'], 'mcp': suggestion['retrieval']['status'],
                      'action_status': action['status'] if action else None}, ensure_ascii=False))


if __name__ == '__main__':
    main()
