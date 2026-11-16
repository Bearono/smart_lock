"""Authenticated ARM lock simulator; use only with the explicit simulator profile."""

import hmac
import os
from pathlib import Path
import platform
import sqlite3

from flask import Flask, jsonify, request
from smartlock_protocol.command_auth import verify
from state import StateStore
from viewer import viewer_token


def create_app(secret, state_path, *, allow_faults=False, clock=None):
    if not isinstance(secret, str) or len(secret.encode()) < 32:
        raise ValueError("Simulator requires an independent secret of at least 32 bytes")
    app = Flask(__name__, static_folder=Path(__file__).with_name("static"))
    app.config["MAX_CONTENT_LENGTH"] = 4096
    store = StateStore(state_path, **({"clock": clock} if clock else {}))
    display_token = viewer_token(secret)

    @app.before_request
    def authenticate():
        if request.method == "GET" and request.endpoint in ("ready", "panel", "static"):
            return None
        if request.path == "/panel/state" and request.method == "GET":
            expected = f"Bearer {display_token}"
            authorization = request.headers.get("Authorization", "")
            if not hmac.compare_digest(authorization.encode(), expected.encode()):
                return jsonify(msg="Display authorization required"), 401
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

    @app.after_request
    def response_policy(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self'; font-src 'self'; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/panel")
    def panel():
        return app.send_static_file("panel.html")

    @app.get("/panel/state")
    def panel_state():
        return jsonify(**store.read(include_commands=True), architecture=platform.machine())

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
