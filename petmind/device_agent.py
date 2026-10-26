"""Music agent: persist a received command before completing it.

By default it is virtual (nothing is played). With --play it plays calm music on this PC's speaker (Windows) and says so
in the acknowledgement (simulated=false). Playing needs the explicit flag; the launcher passes it only for -Speaker.
"""
import argparse
import json
import sqlite3
import threading
import time
from pathlib import Path

import requests

from petmind import music


class SpeakerPlayer:
    """Plays a WAV through the default output with winsound, for at most `seconds`."""

    def __init__(self, music_dir, seconds=60):
        self.music_dir, self.seconds, self.timer = Path(music_dir), seconds, None

    def start(self, style):
        try:
            import winsound
        except ImportError as exc:
            raise RuntimeError('speaker playback is only available on Windows') from exc
        path = music.music_file(self.music_dir, style or 'calm_piano', self.seconds)
        if self.timer is not None:
            self.timer.cancel()
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)  # replaces anything still playing
        self.timer = threading.Timer(self.seconds, lambda: winsound.PlaySound(None, winsound.SND_PURGE))
        self.timer.daemon = True
        self.timer.start()
        return f'PC 스피커로 재생 시작: {path.name} (최대 {self.seconds}초)'


def run_once(base, cache_path, outcome='completed', command_id_filter=None, player=None):
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
            detail = 'virtual music; no physical playback'
            if player is not None and inserted:  # a retried command is acknowledged again but never played twice
                try:
                    detail = player.start((action.get('request') or {}).get('style'))
                except Exception as exc:  # noqa: BLE001 - any playback problem is reported to the guardian
                    detail = f'재생하지 못했습니다: {type(exc).__name__}: {exc}'
                    cache.execute('UPDATE commands SET outcome=? WHERE id=?', ('failed', command_id))
                    cache.commit()
            elif player is not None:
                detail = 'PC 스피커 명령(이미 처리함)'
            terminal = cache.execute('SELECT outcome FROM commands WHERE id=?', (command_id,)).fetchone()[0]
            response = requests.post(ack_url, json={'status': terminal, 'detail': detail, 'simulated': player is None}, timeout=5)
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
    parser.add_argument('--play', action='store_true', help="play the music on this PC's speaker instead of only pretending")
    parser.add_argument('--music-dir', type=Path, default=Path('artifacts/music'),
                        help='<style>.wav here is played as is; otherwise a quiet piece is generated')
    parser.add_argument('--seconds', type=int, default=60, help='longest playback per command')
    args = parser.parse_args()
    player = SpeakerPlayer(args.music_dir, args.seconds) if args.play else None
    while True:
        try:
            print(json.dumps(run_once(args.base.rstrip('/'), args.cache, args.outcome, args.command_id, player), ensure_ascii=False), flush=True)
        except requests.RequestException as exc:
            print(f'Virtual device connection failed: {type(exc).__name__}', flush=True)
            if args.once:
                raise
        if args.once:
            break
        time.sleep(2)


if __name__ == '__main__':
    main()
