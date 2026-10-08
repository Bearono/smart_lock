"""Authenticate backend commands and persist replay protection across device restarts."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import time
from contextlib import closing
from flask import request, jsonify


def register_command_guard(app, transmitter):
    app.config['MAX_CONTENT_LENGTH'] = 64 * 1024

    @app.before_request
    def authenticate_command():
        if request.method != 'POST':
            return None
        stamp, nonce, signature = (request.headers.get(k, '') for k in ('X-Command-Time', 'X-Command-Nonce', 'X-Command-Signature'))
        if (not stamp.isascii() or not stamp.isdigit() or len(stamp) > 12
                or abs(time.time() - int(stamp)) > 60 or len(nonce) != 32
                or any(c not in '0123456789abcdef' for c in nonce)
                or len(signature) != 64 or any(c not in '0123456789abcdef' for c in signature)):
            return jsonify(status='error', msg='Authenticated command required'), 401
        body = request.get_data()
        message = json.dumps([request.method, request.path, stamp, nonce, hashlib.sha256(body).hexdigest()], separators=(',', ':')).encode()
        key = hashlib.sha256(b'smart-lock-backend-command\0' + transmitter.device_password.encode()).digest()
        expected = hmac.new(key, message, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return jsonify(status='error', msg='Invalid command signature'), 401
        path = Path(os.environ.get('DEVICE_STATE_DIR', str(Path(__file__).parent / 'instance'))) / 'commands.db'
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path, timeout=5)) as connection, connection:
            connection.execute('CREATE TABLE IF NOT EXISTS receipts (nonce TEXT PRIMARY KEY, expires REAL NOT NULL)')
            connection.execute('DELETE FROM receipts WHERE expires < ?', (time.time(),))
            try:
                connection.execute('INSERT INTO receipts VALUES (?, ?)', (nonce, int(stamp) + 60))
            except sqlite3.IntegrityError:
                return jsonify(status='error', msg='Command already received'), 409
        if request.is_json and not isinstance(request.get_json(silent=True), dict):
            return jsonify(status='error', msg='JSON request body must be an object'), 400
        return None
