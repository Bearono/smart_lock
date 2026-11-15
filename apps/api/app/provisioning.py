"""Operator-managed device identity and endpoint; device telemetry never selects URLs."""
import re
from urllib.parse import urlsplit
from flask import current_app
from cryptography.fernet import InvalidToken
from app.models import DeviceProvisioning
from app.security_store import _cipher, SecurePayloadError


def validate_device_id(device_id):
    return isinstance(device_id, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,50}', device_id) is not None


def validate_service_url(url):
    parts = urlsplit(url)
    if (parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password
            or parts.query or parts.fragment or parts.path not in ('', '/')):
        raise ValueError('Device URL must be an http(s) origin without credentials, path, query or fragment')
    if parts.port is not None and not 1 <= parts.port <= 65535:
        raise ValueError('Invalid port')
    if (current_app.config['DEPLOYMENT_ENV'] == 'production' and parts.scheme != 'https'
            and parts.hostname not in ('localhost', '127.0.0.1', '::1')):
        raise ValueError('Production device endpoints require HTTPS; HTTP is limited to loopback test services')
    return url.rstrip('/')


def device_credentials(device_id):
    """Return the secret and its immutable storage snapshot for handshake admission."""
    provision = DeviceProvisioning.query.filter_by(device_id=device_id).first()
    if provision and provision.enabled:
        try:
            return _cipher().decrypt(provision.encrypted_password).decode(), bytes(provision.encrypted_password)
        except InvalidToken as exc:
            raise SecurePayloadError('Device must be reprovisioned', 'DEVICE_NOT_PROVISIONED', 403) from exc
    if not provision and current_app.config['ALLOW_DEMO_DEVICES']:
        return 'ChangeMe-Spake2-Device-Password', None
    raise SecurePayloadError('Device is not provisioned or has been disabled', 'DEVICE_NOT_PROVISIONED', 403)


def device_password(device_id):
    return device_credentials(device_id)[0]


def revoke_device_capabilities(device_id):
    """Caller commits identity changes, revocations and audit together."""
    from app.models import AuthSession, DeviceSecuritySession, GuestPass, UnlockToken
    from app.door_commands import revoke_pending
    DeviceSecuritySession.query.filter_by(device_id=device_id).delete(synchronize_session=False)
    AuthSession.query.filter_by(device_id=device_id).filter(
        AuthSession.status.in_(['pending', 'processing', 'face_verified', 'totp_required'])
    ).update({'status': 'failed'}, synchronize_session='fetch')
    UnlockToken.query.filter_by(device_id=device_id).update({'is_used': True}, synchronize_session='fetch')
    GuestPass.query.filter_by(device_id=device_id).update({'is_active': False}, synchronize_session='fetch')
    revoke_pending(device_id)
