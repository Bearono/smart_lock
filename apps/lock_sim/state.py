"""Transactional simulated bolt state. This module never claims a physical sensor."""

from contextlib import closing
import math
from pathlib import Path
import re
import sqlite3
import time

MODES = ("normal", "jammed", "feedback_lost")


class StateStore:
    def __init__(self, path, clock=time.time):
        self.path, self.clock = Path(path), clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS bolt (id INTEGER PRIMARY KEY CHECK(id=1), state TEXT NOT NULL, fault TEXT NOT NULL)"
            )
            db.execute("INSERT OR IGNORE INTO bolt VALUES (1,'LOCKED','normal')")
            db.execute(
                "CREATE TABLE IF NOT EXISTS commands (id TEXT PRIMARY KEY, target TEXT NOT NULL, expires REAL NOT NULL, observed TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS nonces (nonce TEXT PRIMARY KEY, expires REAL NOT NULL)"
            )

    def connect(self):
        return closing(sqlite3.connect(self.path, timeout=3))

    def claim(self, nonce, expires):
        with self.connect() as db, db:
            db.execute("DELETE FROM nonces WHERE expires < ?", (self.clock(),))
            db.execute("INSERT INTO nonces VALUES (?,?)", (nonce, expires))

    def read(self):
        with self.connect() as db:
            state, fault = db.execute("SELECT state,fault FROM bolt WHERE id=1").fetchone()
            count = db.execute("SELECT count(*) FROM commands").fetchone()[0]
        return {
            "reported_status": "UNKNOWN" if fault == "feedback_lost" else state,
            "execution_mode": "SIMULATED",
            "fault": fault,
            "command_count": count,
        }

    def execute(self, command):
        identity, target, expires = (
            command.get(key) for key in ("id", "target_status", "expires_at")
        )
        if (
            not isinstance(identity, str)
            or not re.fullmatch("[0-9a-f]{32}", identity)
            or target not in ("LOCKED", "UNLOCKED")
            or type(expires) not in (int, float)
            or not math.isfinite(expires)
        ):
            raise ValueError("Invalid command")
        now = self.clock()
        if not now < expires <= now + 60:
            raise ValueError("Command expired or exceeds allowed lifetime")
        with self.connect() as db, db:
            db.execute("BEGIN IMMEDIATE")
            if self.clock() >= expires:
                raise ValueError("Command expired while waiting for simulated actuator")
            previous = db.execute(
                "SELECT target,expires,observed FROM commands WHERE id=?", (identity,)
            ).fetchone()
            if previous:
                if previous[:2] != (target, expires):
                    raise ValueError("Command identity reused with different content")
                observed = previous[2]
            else:
                state, fault = db.execute("SELECT state,fault FROM bolt WHERE id=1").fetchone()
                if fault != "jammed":
                    state = target
                    db.execute("UPDATE bolt SET state=? WHERE id=1", (state,))
                observed = "UNKNOWN" if fault == "feedback_lost" else state
                db.execute(
                    "INSERT INTO commands VALUES (?,?,?,?)", (identity, target, expires, observed)
                )
                db.execute("DELETE FROM commands WHERE expires < ?", (now - 86400,))
        return {
            "id": identity,
            "reported_status": observed,
            "execution_mode": "SIMULATED",
            "status": "executed" if observed == target else "failed",
        }

    def set_fault(self, fault):
        if fault not in MODES:
            raise ValueError("Unknown simulation fault")
        with self.connect() as db, db:
            db.execute("UPDATE bolt SET fault=? WHERE id=1", (fault,))
        return self.read()
