"""Verify failure and a real elapsed device timeout over HTTP (no DB timestamp edits)."""
import json
import time
import uuid
from pathlib import Path

from scripts.verify_flow import BASE, request
from petmind.device_agent import run_once


def command(pet):
    observation = request('POST', '/demo/observe', json={'pet_id': pet, 'scenario': 'anxious'})
    suggestion = request('POST', '/care/evaluate', json={'observation_id': observation['id']})
    return request('POST', f'/care/{suggestion["id"]}/approve', json={})


def main():
    pet = 'fault-verify-' + uuid.uuid4().hex[:8]
    failed = command(pet)
    run_once(BASE, Path('device_fault_commands.db'), outcome='failed')
    result = next(row for row in request('GET', f'/care/actions/recent?pet_id={pet}') if row['id'] == failed['id'])
    assert result['status'] == 'failed'
    no_response = command(pet)
    start = time.monotonic()
    while time.monotonic()-start < 60:
        rows = request('GET', f'/care/actions/recent?pet_id={pet}')
        timed_out = next(row for row in rows if row['id'] == no_response['id'])
        if timed_out['status'] == 'timed_out':
            break
        time.sleep(2)
    assert timed_out['status'] == 'timed_out'
    report = {'pet_id': pet, 'failure': result, 'timeout': timed_out, 'elapsed_wait_seconds': time.monotonic()-start}
    Path('artifacts/fault_verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'failed': result['status'], 'no_response': timed_out['status'],
                      'wait_seconds': report['elapsed_wait_seconds']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
