"""Durable, at-most-once actuation with independently retryable receipts.

Drivers must bound their I/O and return observed state, never desired state.
An interrupted actuation is deliberately not resumed: its outcome is unknown.
"""
from contextlib import closing
import logging
import math
from pathlib import Path
import re
import sqlite3
import time
from threading import Lock
from typing import Protocol

logger = logging.getLogger(__name__)
STATES = frozenset({'LOCKED', 'UNLOCKED'})
RETENTION_SECONDS = 86400


class Actuator(Protocol):
    def set_state(self, target: str) -> None: ...

    def read_state(self) -> str: ...


class UnavailableActuator:
    def set_state(self, target):
        raise RuntimeError('No actuator driver configured')

    def read_state(self):
        return 'UNKNOWN'


class CommandExecutor:
    def __init__(self, transmitter, actuator: Actuator, journal_path, clock=time.time):
        self.transmitter = transmitter
        self.actuator = actuator
        self.path = Path(journal_path)
        self.clock = clock
        self.lock = Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute('''CREATE TABLE IF NOT EXISTS executions (
                id TEXT PRIMARY KEY, target TEXT NOT NULL, expires REAL NOT NULL,
                status TEXT NOT NULL, observed TEXT NOT NULL DEFAULT 'UNKNOWN',
                delivered INTEGER NOT NULL DEFAULT 0)''')

    def _connect(self):
        # Autocommit makes every journal transition durable before external I/O.
        return closing(sqlite3.connect(self.path, timeout=5, isolation_level=None))

    def _execute(self, command):
        if not isinstance(command, dict):
            raise ValueError('Command must be an object')
        command_id = command.get('id')
        target, expires = command.get('target_status'), command.get('expires_at')
        if (not isinstance(command_id, str) or not re.fullmatch(r'[0-9a-f]{32}', command_id)
                or not isinstance(target, str) or target not in STATES
                or type(expires) not in (int, float) or not math.isfinite(expires)):
            raise ValueError('Invalid command fields')
        now = self.clock()
        if expires <= now:
            return
        if expires > now + 60:
            raise ValueError('Command lifetime exceeds allowed clock skew')
        with self._connect() as connection:
            inserted = connection.execute(
                "INSERT OR IGNORE INTO executions(id,target,expires,status) VALUES(?,?,?,'executing')",
                (command_id, target, expires)).rowcount
            if not inserted:
                previous = connection.execute('SELECT target,expires FROM executions WHERE id=?',
                                              (command_id,)).fetchone()
                if previous != (target, expires):
                    raise ValueError('Command ID reused with different payload')
                return
        status, observed = 'failed', 'UNKNOWN'
        try:
            if self.clock() < expires:
                self.actuator.set_state(target)
                reading = self.actuator.read_state()
                observed = reading if isinstance(reading, str) and reading in STATES else 'UNKNOWN'
                if observed == target and self.clock() < expires:
                    status = 'executed'
        except Exception:
            logger.exception('Command execution failed: %s', command_id)
        with self._connect() as connection:
            connection.execute("UPDATE executions SET status=?,observed=? WHERE id=? AND status='executing'",
                               (status, observed, command_id))

    def _deliver(self):
        now = self.clock()
        with self._connect() as connection:
            # Wait until expiry before recovering an interrupted reservation.
            # Another worker may still own a live reservation; never steal it.
            connection.execute("UPDATE executions SET status='failed' WHERE status='executing' AND expires<=?", (now,))
            connection.execute('DELETE FROM executions WHERE expires<?', (now - RETENTION_SECONDS,))
            receipts = connection.execute(
                "SELECT id,status,observed FROM executions WHERE delivered=0 AND status!='executing' ORDER BY expires DESC LIMIT 1").fetchall()
        for command_id, status, observed in receipts:
            try:
                self.transmitter.acknowledge_command(command_id, status, observed)
            except Exception as exc:
                response = getattr(exc, 'response', None)
                if response is None or response.status_code not in (404, 409):
                    logger.warning('Command receipt deferred: %s', command_id)
                    continue
            with self._connect() as connection:
                connection.execute('UPDATE executions SET delivered=1 WHERE id=?', (command_id,))

    def run_once(self):
        with self.lock:
            try:
                payload = self.transmitter.sync_lock()  # Authenticated by transmitter.
                if not isinstance(payload, dict) or 'command' not in payload:
                    raise ValueError('Invalid sync response')
                if payload['command'] is not None:
                    self._execute(payload['command'])
            finally:
                # A sync outage must not prevent delivery of existing receipts.
                self._deliver()
