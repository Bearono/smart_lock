"""Software actuator fixtures; no GPIO or physical execution."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import importlib.util
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import Mock

from requests import HTTPError, Response

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('device_executor', ROOT / 'paspberry_pi/command_executor.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
CommandExecutor = module.CommandExecutor


class CommandExecutorTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'executions.db'
        self.now = 1000
        self.command = dict(id='a' * 32, target_status='UNLOCKED', expires_at=1030)
        self.transmitter = Mock()
        self.transmitter.sync_lock.return_value = {'command': self.command}
        self.actuator = Mock()
        self.actuator.read_state.return_value = 'UNLOCKED'
        self.executor = self.make_executor()

    def make_executor(self):
        return CommandExecutor(self.transmitter, self.actuator, self.path, clock=lambda: self.now)

    def test_restart_and_duplicate_never_repeat_actuation(self):
        self.executor.run_once()
        self.make_executor().run_once()
        self.actuator.set_state.assert_called_once_with('UNLOCKED')
        self.transmitter.acknowledge_command.assert_called_once_with('a' * 32, 'executed', 'UNLOCKED')

    def test_lost_receipt_retries_without_reexecution_even_if_sync_fails(self):
        self.transmitter.acknowledge_command.side_effect = [TimeoutError(), None]
        self.executor.run_once()
        self.transmitter.sync_lock.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError):
            self.make_executor().run_once()
        self.assertEqual(self.transmitter.acknowledge_command.call_count, 2)
        self.actuator.set_state.assert_called_once()

    def test_reservation_is_committed_before_driver_io(self):
        def inspect(target):
            with closing(sqlite3.connect(self.path)) as connection:
                self.assertEqual(connection.execute('SELECT status FROM executions').fetchone(), ('executing',))
        self.actuator.set_state.side_effect = inspect
        self.executor.run_once()

    def test_process_interruption_is_not_resumed(self):
        self.actuator.set_state.side_effect = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.executor.run_once()
        self.make_executor().run_once()
        self.transmitter.acknowledge_command.assert_not_called()
        self.now = 1031
        self.make_executor().run_once()
        self.actuator.set_state.assert_called_once()
        self.transmitter.acknowledge_command.assert_called_once_with('a' * 32, 'failed', 'UNKNOWN')

    def test_mismatch_and_driver_error_never_report_success(self):
        self.actuator.read_state.return_value = 'LOCKED'
        self.executor.run_once()
        self.transmitter.acknowledge_command.assert_called_with('a' * 32, 'failed', 'LOCKED')
        self.command['id'] = 'b' * 32
        self.actuator.set_state.side_effect = RuntimeError('unavailable')
        self.executor.run_once()
        self.transmitter.acknowledge_command.assert_called_with('b' * 32, 'failed', 'UNKNOWN')

    def test_default_driver_is_explicitly_unavailable(self):
        self.executor.actuator = module.UnavailableActuator()
        self.executor.run_once()
        self.transmitter.acknowledge_command.assert_called_once_with('a' * 32, 'failed', 'UNKNOWN')

    def test_expired_and_invalid_commands_do_not_reach_driver(self):
        self.now = 1030
        self.executor.run_once()
        for fields in ({'expires_at': float('nan')}, {'expires_at': True},
                       {'expires_at': 9999}, {'id': '../bad'}, {'target_status': []}):
            self.transmitter.sync_lock.return_value = {'command': dict(self.command, **fields)}
            with self.assertRaises(ValueError):
                self.executor.run_once()
        self.actuator.set_state.assert_not_called()

    def test_payload_conflict_does_not_reexecute(self):
        self.executor.run_once()
        self.command['target_status'] = 'LOCKED'
        with self.assertRaises(ValueError):
            self.executor.run_once()
        self.actuator.set_state.assert_called_once()

    def test_concurrent_executors_do_not_steal_live_reservation(self):
        entered, release = Event(), Event()
        def actuate(target):
            entered.set()
            if not release.wait(5):
                raise RuntimeError('test coordination timed out')
        self.actuator.set_state.side_effect = actuate
        other = self.make_executor()
        with ThreadPoolExecutor(max_workers=2) as pool:
            future = pool.submit(self.executor.run_once)
            try:
                self.assertTrue(entered.wait(5))
                other.run_once()
                self.transmitter.acknowledge_command.assert_not_called()
            finally:
                release.set()
            future.result(timeout=5)
        self.actuator.set_state.assert_called_once()

    def test_terminal_rejection_stops_receipt_retry(self):
        response = Response()
        response.status_code = 409
        self.transmitter.acknowledge_command.side_effect = HTTPError(response=response)
        self.executor.run_once()
        self.executor.run_once()
        self.transmitter.acknowledge_command.assert_called_once()

    def test_journal_retention_never_allows_expired_reexecution(self):
        self.executor.run_once()
        self.now += 90000
        self.executor.run_once()
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM executions').fetchone()[0], 0)
        self.actuator.set_state.assert_called_once()

    def test_expiry_after_reservation_prevents_driver_call(self):
        ticks = iter([1000, 1031, 1031])
        self.executor.clock = lambda: next(ticks)
        self.executor.run_once()
        self.actuator.set_state.assert_not_called()
        self.transmitter.acknowledge_command.assert_called_once_with('a' * 32, 'failed', 'UNKNOWN')

    def test_worker_lifecycle_and_observed_heartbeat(self):
        spec = importlib.util.spec_from_file_location('device_runtime', ROOT / 'paspberry_pi/runtime.py')
        runtime = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runtime)
        called = Event()
        executor = Mock()
        executor.run_once.side_effect = called.set
        worker = runtime.CommandWorker(executor, interval=30)
        self.addCleanup(worker.stop)
        worker.start()
        worker.start()
        self.assertTrue(called.wait(5))
        worker.stop()
        self.assertFalse(worker.thread.is_alive())
        executor.run_once.assert_called_once()
        camera = Mock()
        heartbeat = runtime.HeartbeatWorker(self.transmitter, camera, actuator=self.actuator)
        heartbeat.report_once()
        self.transmitter.heartbeat.assert_called_with('UNLOCKED', camera_status='ONLINE')
        self.actuator.read_state.side_effect = RuntimeError('sensor offline')
        heartbeat.report_once()
        self.transmitter.heartbeat.assert_called_with('UNKNOWN', camera_status='ONLINE')
