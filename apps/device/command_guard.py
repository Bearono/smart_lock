"""Authenticate backend commands and persist replay protection across device restarts."""
import os
from pathlib import Path
import sqlite3
import time
from contextlib import closing
from flask import request, jsonify
from smartlock_protocol.command_auth import verify


def register_command_guard(app, transmitter):
    app.config['MAX_CONTENT_LENGTH'] = 64 * 1024

    @app.before_request
    def authenticate_command():
        if request.method != 'POST':
            return None
        try:
            nonce, expires = verify(transmitter.device_password, request.method, request.path,
                                    request.get_data(), request.headers)
        except ValueError as error:
            return jsonify(status='error', msg=str(error)), 401
        path = Path(os.environ.get('DEVICE_STATE_DIR', str(Path(__file__).parent / 'instance'))) / 'commands.db'
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path, timeout=5)) as connection, connection:
            connection.execute('CREATE TABLE IF NOT EXISTS receipts (nonce TEXT PRIMARY KEY, expires REAL NOT NULL)')
            connection.execute('DELETE FROM receipts WHERE expires < ?', (time.time(),))
            try:
                connection.execute('INSERT INTO receipts VALUES (?, ?)', (nonce, expires))
            except sqlite3.IntegrityError:
                return jsonify(status='error', msg='Command already received'), 409
        if request.is_json and not isinstance(request.get_json(silent=True), dict):
            return jsonify(status='error', msg='JSON request body must be an object'), 400
        return None
