"""Shared fixed-window admission limits; rejected attempts do not extend lockouts."""
import hashlib
import time
from flask import current_app, request, jsonify
from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app import db
from app.models import RateLimitBucket


def admit(scope, identity, limit, window=60):
    now = time.time()
    slot = int(now // window)
    key = hashlib.sha256(f'{scope}\0{identity}\0{slot}'.encode()).hexdigest()
    expiry = (slot + 1) * window
    with Session(db.engine) as store, store.begin():
        store.execute(delete(RateLimitBucket).where(RateLimitBucket.expires_at <= now))
        try:
            with store.begin_nested():
                store.add(RateLimitBucket(key=key, count=0, expires_at=expiry))
                store.flush()
        except IntegrityError:
            pass
        result = store.execute(update(RateLimitBucket).where(
            RateLimitBucket.key == key, RateLimitBucket.count < limit,
        ).values(count=RateLimitBucket.count + 1))
        return result.rowcount == 1, max(1, int(expiry - now) + 1)


def register(app):
    paths = {
        '/api/login': 30, '/api/login/pre': 30, '/api/register': 10,
        '/api/login/mfa/verify': 30, '/api/login/mfa/bind': 30,
        '/api/security/spake2/start': 30, '/api/mfa/guest/verify': 30,
        '/api/security/spake2/confirm': 30,
        '/api/lock/unlock-token/verify': 60,
        '/api/lock/command-status': 120,
        '/api/mfa/verify/totp': 10,
        '/api/account/password': 5,
    }

    @app.before_request
    def limit_sensitive_requests():
        if request.method != 'POST' or request.path not in paths or not current_app.config.get('RATE_LIMIT_ENABLED', True):
            return None
        allowed, retry = admit(request.path, request.remote_addr or 'unknown', paths[request.path])
        if allowed and request.path in ('/api/login', '/api/login/pre'):
            data = request.get_json(silent=True) or {}
            username = data.get('username')
            if isinstance(username, str):
                allowed, retry = admit('password-account', username[:80], 10, 300)
        if not allowed:
            return jsonify(msg='Too many attempts; try again later', code='RATE_LIMITED'), 429, {'Retry-After': str(retry)}
        return None
