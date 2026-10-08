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
    return url.rstrip('/')


def device_password(device_id):
    provision = DeviceProvisioning.query.filter_by(device_id=device_id).first()
    if provision and provision.enabled:
        try:
            return _cipher().decrypt(provision.encrypted_password).decode()
        except InvalidToken as exc:
            raise SecurePayloadError('Device must be reprovisioned', 'DEVICE_NOT_PROVISIONED', 403) from exc
    if not provision and current_app.config['ALLOW_DEMO_DEVICES']:
        return 'ChangeMe-Spake2-Device-Password'
    raise SecurePayloadError('Device is not provisioned or has been disabled', 'DEVICE_NOT_PROVISIONED', 403)
