"""Authenticated ARM lock simulator; use only with the explicit simulator profile."""

import os
from pathlib import Path
import platform
import sqlite3

from flask import Flask, jsonify, request
from smartlock_protocol.command_auth import verify
from state import StateStore


def create_app(secret, state_path, *, allow_faults=False, clock=None):
    if not isinstance(secret, str) or len(secret.encode()) < 32:
        raise ValueError("Simulator requires an independent secret of at least 32 bytes")
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 4096
    store = StateStore(state_path, **({"clock": clock} if clock else {}))

    @app.before_request
    def authenticate():
        if request.path == "/health/ready" and request.method == "GET":
            return None
        if request.method != "POST":
            return jsonify(msg="Authenticated POST required"), 405
        try:
            nonce, expires = verify(
                secret,
                request.method,
                request.path,
                request.get_data(),
                request.headers,
                **({"now": clock()} if clock else {}),
            )
            store.claim(nonce, expires)
        except ValueError as error:
            return jsonify(msg=str(error)), 401
        except sqlite3.IntegrityError:
            return jsonify(msg="Command already received"), 409
        if not request.is_json or not isinstance(request.get_json(silent=True), dict):
            return jsonify(msg="JSON object required"), 400

    @app.get("/health/ready")
    def ready():
        store.read()
        return jsonify(status="ok", execution_mode="SIMULATED", architecture=platform.machine())

    @app.post("/state")
    def state():
        return jsonify(store.read())

    @app.post("/commands")
    def execute():
        try:
            return jsonify(store.execute(request.get_json()))
        except ValueError as error:
            return jsonify(msg=str(error)), 400

    @app.post("/fault")
    def fault():
        if not allow_faults:
            return jsonify(msg="Fault injection is disabled"), 403
        try:
            return jsonify(store.set_fault(request.get_json().get("fault")))
        except ValueError as error:
            return jsonify(msg=str(error)), 400

    return app


def from_environment():
    if os.environ.get("SMART_LOCK_SIMULATION") != "true":
        raise ValueError("Explicit SMART_LOCK_SIMULATION=true is required")
    secret = Path(os.environ["SIMULATOR_SECRET_FILE"]).read_text().strip()
    return create_app(
        secret,
        Path(os.environ.get("DEVICE_STATE_DIR", "/data")) / "lock.db",
        allow_faults=os.environ.get("SIMULATOR_ALLOW_FAULTS") == "true",
    )
