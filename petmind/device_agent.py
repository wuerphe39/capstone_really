"""PC/Pi-compatible virtual music agent: persist a received command before completing it."""
import argparse
import json
import sqlite3
import time
from pathlib import Path

import requests


def run_once(base, cache_path, outcome='completed', command_id_filter=None):
    with sqlite3.connect(cache_path) as cache:
        cache.execute('CREATE TABLE IF NOT EXISTS commands (id TEXT PRIMARY KEY, outcome TEXT NOT NULL)')
        response = requests.get(f'{base}/care/actions/pending', timeout=5)
        response.raise_for_status()
        handled = []
        for action in response.json():
            command_id = action['command_id']
            if command_id_filter is not None and command_id != command_id_filter:
                continue
            ack_url = f'{base}/care/actions/{command_id}/ack'
            if action['status'] == 'requested':
                response = requests.post(ack_url, json={'status': 'acknowledged'}, timeout=5)
                if response.status_code == 409:
                    continue
                response.raise_for_status()
            # Atomic local claim: two agents sharing a cache must not race between
            # SELECT and INSERT or disagree about a retried command's outcome.
            inserted = cache.execute('INSERT OR IGNORE INTO commands VALUES (?, ?)', (command_id, outcome)).rowcount == 1
            cache.commit()
            terminal = cache.execute('SELECT outcome FROM commands WHERE id=?', (command_id,)).fetchone()[0]
            response = requests.post(ack_url, json={'status': terminal, 'detail': 'virtual music; no physical playback'}, timeout=5)
            if response.status_code != 409:
                response.raise_for_status()
            handled.append({'command_id': command_id, 'status': terminal, 'replayed_ack': not inserted})
        return handled


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://127.0.0.1:8010')
    parser.add_argument('--cache', type=Path, default=Path('device_commands.db'))
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--outcome', choices=['completed', 'failed'], default='completed')
    parser.add_argument('--command-id', help='Handle only this command during an isolated test')
    args = parser.parse_args()
    while True:
        try:
            print(json.dumps(run_once(args.base.rstrip('/'), args.cache, args.outcome, args.command_id), ensure_ascii=False), flush=True)
        except requests.RequestException as exc:
            print(f'Virtual device connection failed: {type(exc).__name__}', flush=True)
            if args.once:
                raise
        if args.once:
            break
        time.sleep(2)


if __name__ == '__main__':
    main()
