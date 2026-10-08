"""Shared device sessions and atomic replay receipts, independent of business transactions."""
import base64
import hashlib
import time

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import db
from app.models import DeviceSecuritySession, SecureMessageReceipt


class SecurePayloadError(ValueError):
    def __init__(self, message, code='INVALID_SECURE_PAYLOAD', status=400):
        super().__init__(message)
        self.code = code
        self.status = status


def _cipher():
    # A stable SECRET_KEY is required across workers/restarts. Rotating it invalidates sessions.
    key = current_app.config['SECRET_KEY']
    if isinstance(key, str):
        key = key.encode('utf-8')
    material = hashlib.sha256(b'smart-lock-device-session-storage\0' + key).digest()
    return Fernet(base64.urlsafe_b64encode(material))


def _prune(store, now):
    store.execute(delete(SecureMessageReceipt).where(SecureMessageReceipt.expires_at < now))
    store.execute(delete(DeviceSecuritySession).where(DeviceSecuritySession.expires_at < now))


def save_session(session, *, protocol_version='SL-SEC-v2', confirmed=True, transcript=None):
    with Session(db.engine) as store, store.begin():
        _prune(store, time.time())
        store.add(DeviceSecuritySession(id=session.session_id, device_id=session.device_id,
                                        encrypted_key=_cipher().encrypt(session.session_key),
                                        protocol_version=protocol_version, confirmed=confirmed, transcript=transcript,
                                        expires_at=session.expires_at))


def load_session(session_id, *, allow_pending=False):
    from app.routes.security_protocol import SecuritySession
    with Session(db.engine) as store:
        record = store.get(DeviceSecuritySession, session_id)
        if not record or record.expires_at <= time.time():
            raise SecurePayloadError('Unknown or expired security session', 'SECURITY_SESSION_INVALID', 401)
        if not record.confirmed and not allow_pending:
            raise SecurePayloadError('Security session requires confirmation', 'SECURITY_SESSION_UNCONFIRMED', 401)
        try:
            key = _cipher().decrypt(record.encrypted_key)
        except InvalidToken as exc:
            raise SecurePayloadError('Security session key changed', 'SECURITY_SESSION_INVALID', 401) from exc
        session = SecuritySession(record.id, record.device_id, key, record.expires_at)
        session.protocol_version = record.protocol_version
        session.confirmed = record.confirmed
        session.transcript_bytes = record.transcript
        return session


def claim_message(session, request_id, nonce, valid_until):
    # A separate committed transaction burns a valid envelope even when business validation fails.
    # Unique constraints arbitrate concurrent requests from any worker; no cache clearing loophole.
    try:
        with Session(db.engine) as store, store.begin():
            now = time.time()
            _prune(store, now)
            if session.expires_at <= now or valid_until < now:
                raise SecurePayloadError('Secure message expired')
            if not store.get(DeviceSecuritySession, session.session_id):
                raise SecurePayloadError('Security session revoked', 'SECURITY_SESSION_INVALID', 401)
            store.add(SecureMessageReceipt(session_id=session.session_id, request_id=request_id,
                                           nonce=nonce, expires_at=session.expires_at))
            # Keep nonce claims for the whole key lifetime, not only the timestamp window.
    except IntegrityError as exc:
        raise SecurePayloadError('Replay attack detected', 'SECURE_MESSAGE_REPLAY') from exc
