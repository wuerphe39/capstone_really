import time
import unittest
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import requests

from scripts import pi_outing_agent as agent
from scripts.monitor_audio_events import STALL_SECONDS, capture_stalled


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeProcess:
    """Runs for `polls` polls, then exits with `code`; exits with 0 once the stop file exists if stop_aware."""

    def __init__(self, folder, polls=1, code=1, stop_aware=False):
        self.folder, self.polls, self.code, self.stop_aware = folder, polls, code, stop_aware
        self.returncode = None
        self.pid = 1

    def poll(self):
        if self.returncode is not None:
            return self.returncode
        if self.stop_aware and (self.folder / 'stop').exists():
            self.returncode = 0
        elif self.polls <= 0:
            self.returncode = self.code
        else:
            self.polls -= 1
        return self.returncode


class Harness:
    def __init__(self, folder, processes, replies=None):
        self.folder, self.processes, self.replies = folder, list(processes), replies
        self.started = 0
        self.states = []
        self.clock = FakeClock()
        self.args = Namespace(base='http://x', pet_id='p', input_args_file=Path('a.json'), ffmpeg='ffmpeg',
                              video_map='0:v:0', audio_map='1:a:0', preview_port=18081)

    def popen(self, command, **kwargs):
        self.started += 1
        return self.processes.pop(0)

    def post(self, route, state):
        self.states.append(state)
        reply = self.replies(len(self.states)) if self.replies else {}
        if isinstance(reply, Exception):
            raise reply
        now = time.time()
        return {'server_time': datetime.now(timezone.utc).isoformat(), **reply}, now, now

    def run(self, redetect=None):
        with mock.patch.object(agent, 'terminate_tree', lambda process: None):
            return agent.supervise(self.args, {'outing_id': 'o'}, self.folder, self.post, '/capture/o/heartbeat',
                                   popen=self.popen, sleep=self.clock.sleep, monotonic=self.clock.monotonic,
                                   redetect=redetect)


class SuperviseTests(unittest.TestCase):
    def test_crash_is_restarted_and_capture_continues_until_stop(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            h = Harness(folder, [FakeProcess(folder, polls=1, code=1), FakeProcess(folder, polls=1000, stop_aware=True)],
                        replies=lambda n: {'stop': n >= 8})
            self.assertEqual(h.run(), 'stopped')
            self.assertEqual(h.started, 2)
            self.assertIn('starting', h.states)  # heartbeats keep flowing while it reconnects

    def test_gives_up_after_repeated_immediate_crashes(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            h = Harness(folder, [FakeProcess(folder, polls=0, code=1) for _ in range(agent.MAX_RESTARTS + 1)])
            self.assertEqual(h.run(), 'failed')
            self.assertEqual(h.started, agent.MAX_RESTARTS + 1)

    def test_long_healthy_run_resets_the_restart_counter(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            polls = int(agent.HEALTHY_RUN_SECONDS / 2) + 1  # each poll is a 2 s heartbeat
            procs = [FakeProcess(folder, polls=polls, code=1) for _ in range(agent.MAX_RESTARTS + 2)]
            procs.append(FakeProcess(folder, polls=0, code=0, stop_aware=True))
            h = Harness(folder, procs, replies=lambda n: {'stop': False})
            # Never fails because every worker ran long enough; end the test by requesting stop late.
            h.replies = lambda n: {'stop': h.started >= agent.MAX_RESTARTS + 3}
            self.assertEqual(h.run(), 'stopped')
            self.assertGreater(h.started, agent.MAX_RESTARTS + 1)

    def test_brief_backend_outage_does_not_stop_capture(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            outage = requests.ConnectionError('down')
            h = Harness(folder, [FakeProcess(folder, polls=6, code=0)],
                        replies=lambda n: outage if n <= agent.HEARTBEAT_FAILURES_BEFORE_STOP - 1 else {})
            # The worker ends by itself (code 0) without any stop request, so it is restarted, then gives up.
            h.processes += [FakeProcess(folder, polls=0, code=1) for _ in range(agent.MAX_RESTARTS)]
            h.run()
            self.assertFalse((folder / 'stop').exists())

    def test_long_backend_outage_requests_a_stop(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            outage = requests.ConnectionError('down')
            h = Harness(folder, [FakeProcess(folder, polls=1000, stop_aware=True)], replies=lambda n: outage)
            self.assertEqual(h.run(), 'stopped')
            self.assertTrue((folder / 'stop').exists())
            self.assertEqual(len(h.states), agent.HEARTBEAT_FAILURES_BEFORE_STOP)

    def test_stop_during_reconnect_wait_ends_without_restarting(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            h = Harness(folder, [FakeProcess(folder, polls=0, code=1)], replies=lambda n: {'stop': n >= 2})
            self.assertEqual(h.run(), 'stopped')
            self.assertEqual(h.started, 1)


class RedetectTests(unittest.TestCase):
    def test_waits_for_an_unplugged_device_without_using_up_restarts(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            answers = iter([True, False, False, False, True])  # start ok; crash; missing x3; back
            h = Harness(folder, [FakeProcess(folder, polls=1, code=1), FakeProcess(folder, polls=1000, stop_aware=True)],
                        replies=lambda n: {'stop': n >= 14})
            self.assertEqual(h.run(redetect=lambda: next(answers)), 'stopped')
            self.assertEqual(h.started, 2)
            self.assertGreaterEqual(h.states.count('starting'), 3)  # heartbeats kept flowing while it waited

    def test_gives_up_when_the_device_never_returns(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            h = Harness(folder, [])
            self.assertEqual(h.run(redetect=lambda: False), 'failed')
            self.assertEqual(h.started, 0)
            self.assertGreaterEqual(h.clock.now, agent.DEVICE_WAIT_SECONDS)

    def test_stop_request_while_waiting_for_the_device(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            h = Harness(folder, [], replies=lambda n: {'stop': n >= 3})
            self.assertEqual(h.run(redetect=lambda: False), 'stopped')
            self.assertEqual(h.started, 0)

    def test_a_crashing_lookup_is_treated_as_not_found(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            calls = []
            def lookup():
                calls.append(1)
                if len(calls) == 1: raise RuntimeError('ffmpeg hung')
                return True
            h = Harness(folder, [FakeProcess(folder, polls=1000, stop_aware=True)], replies=lambda n: {'stop': n >= 4})
            self.assertEqual(h.run(redetect=lookup), 'stopped')
            self.assertEqual(h.started, 1)

    def test_without_redetect_nothing_is_looked_up(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            h = Harness(folder, [FakeProcess(folder, polls=1000, stop_aware=True)], replies=lambda n: {'stop': n >= 2})
            self.assertEqual(h.run(), 'stopped')


class StallTests(unittest.TestCase):
    def test_stall_only_after_the_limit_and_never_while_stopping(self):
        self.assertFalse(capture_stalled(STALL_SECONDS - 1, False))
        self.assertTrue(capture_stalled(STALL_SECONDS + 1, False))
        self.assertFalse(capture_stalled(STALL_SECONDS + 100, True))


if __name__ == '__main__':
    unittest.main()
