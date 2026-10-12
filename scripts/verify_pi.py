"""Actual PC HTTP -> SSH tunnel -> Pi agent -> PC persistence verification."""
import json
import subprocess
import time
import uuid
from pathlib import Path

import requests

from scripts.verify_flow import request

SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', '-o', 'StrictHostKeyChecking=yes', 'raspberrypi-ai']
FOLDER = '/home/pi/Desktop/PetMind_Test'


def remote(*args):
    result = subprocess.run(SSH + list(args), capture_output=True, text=True, encoding='utf-8', timeout=30)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f'Pi exit {result.returncode}')
    return json.loads(result.stdout)


def create_command(pet):
    observation = request('POST', '/demo/observe', json={'pet_id': pet, 'scenario': 'anxious'})
    suggestion = request('POST', '/care/evaluate', json={'observation_id': observation['id'],
        'question': '가상 장치 왕복 시험용 합성 관찰입니다. 반복 신호를 확인하고 적절하다면 보호자가 승인할 음악을 제안해 주세요.'})
    if 'music' not in suggestion['recommended_actions']:
        raise RuntimeError('No music suggested; command test not executed')
    action = request('POST', f'/care/{suggestion["id"]}/approve', json={})
    return suggestion, action


def actions(pet):
    return request('GET', f'/care/actions/recent?pet_id={pet}')


def main():
    pet = 'pi-test-' + uuid.uuid4().hex[:8]
    request('POST', '/demo/seed', json={'pet_id': pet})
    report = {'pet_id': pet, 'pi': remote(f'{FOLDER}/.venv/bin/python', f'{FOLDER}/pi_probe.py'),
              'transport': 'SSH reverse tunnel; Pi loopback 18010 -> PC loopback 8010', 'tests': []}
    for outcome in ['completed', 'failed']:
        suggestion, action = create_command(pet)
        args = [f'{FOLDER}/.venv/bin/python', f'{FOLDER}/device_agent.py', '--base', 'http://127.0.0.1:18010',
                '--cache', f'{FOLDER}/commands.db', '--once', '--outcome', outcome, '--command-id', action['command_id']]
        received = remote(*args)
        assert len(received) == 1 and received[0]['command_id'] == action['command_id']
        terminal = next(row for row in actions(pet) if row['command_id'] == action['command_id'])
        assert terminal['status'] == outcome
        retry = remote(*args)
        assert retry == []  # terminal command is no longer pending
        stale = requests.post(f'http://127.0.0.1:8010/care/actions/{action["command_id"]}/ack',
                              json={'status': 'acknowledged'}, timeout=5)
        assert stale.status_code == 409
        report['tests'].append({'outcome': outcome, 'provider': suggestion['provider'],
                                'received_on_pi': received, 'stored_on_pc': terminal,
                                'duplicate_poll_result': retry, 'late_ack_status': stale.status_code})
        print(f'Pi {outcome}: received, persisted, duplicate and late ACK checks passed', flush=True)
    _, timeout_action = create_command(pet)
    start = time.monotonic()
    while time.monotonic()-start < 60:
        timeout_result = next(row for row in actions(pet) if row['command_id'] == timeout_action['command_id'])
        if timeout_result['status'] == 'timed_out':
            break
        time.sleep(2)
    assert timeout_result['status'] == 'timed_out'
    report['tests'].append({'outcome': 'timed_out', 'stored_on_pc': timeout_result,
                            'elapsed_wait_seconds': time.monotonic()-start})
    for folder in [Path('artifacts'), Path('docs/evidence')]:
        (folder/'pi_verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('All Pi protocol tests passed; music was simulated, no physical playback', flush=True)


if __name__ == '__main__':
    main()
