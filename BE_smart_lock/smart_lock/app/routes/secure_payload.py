"""Validate authenticated envelopes before claiming them or running business code."""
import base64
import json
import time
from pathlib import Path

from flask import current_app, request
from cryptography.exceptions import InvalidTag
from smartlock_protocol.v3 import VERSION, Envelope
from cryptography.hazmat.primitives import padding, serialization
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.security_store import load_session, claim_message, SecurePayloadError
from .security_protocol import (MAX_CLOCK_SKEW_SECONDS, PROTOCOL_VERSION, SecureEnvelope,
                                b64d, canonical_json, constant_time_equal, hmac_sha256)

PRIVATE_KEY_PATH = Path(__file__).resolve().parents[2] / 'backend_priv.pem'


def _text(value, name, maximum):
    if not isinstance(value, str) or not 1 <= len(value) <= maximum:
        raise ValueError('Invalid ' + name)
    return value


def _reject_constant(value):
    raise ValueError('Non-finite JSON number: ' + value)


def _decrypt_v2(packet):
    header = packet['header']
    session_id = _text(header.get('session_id'), 'session_id', 32)
    device_id = _text(header.get('device_id'), 'device_id', 50)
    request_id = _text(header.get('request_id'), 'request_id', 64)
    nonce = _text(header.get('nonce'), 'nonce', 64)
    timestamp = header.get('timestamp')
    if type(timestamp) is not int or abs(time.time() - timestamp) > MAX_CLOCK_SKEW_SECONDS:
        raise ValueError('Invalid or expired message timestamp')
    if len(b64d(nonce)) != 16:
        raise ValueError('Nonce must contain 16 bytes')
    iv = b64d(packet.get('iv'))
    mac = b64d(packet.get('mac'))
    ciphertext = b64d(packet.get('ciphertext'))
    if len(iv) != 16 or len(mac) != 32 or not ciphertext or len(ciphertext) % 16:
        raise ValueError('Invalid IV, MAC or ciphertext length')

    session = load_session(session_id)
    if getattr(session, 'protocol_version', PROTOCOL_VERSION) != PROTOCOL_VERSION:
        raise ValueError('Session protocol mismatch')
    if session.device_id != device_id:
        raise ValueError('Device/session mismatch')
    enc_key, mac_key = SecureEnvelope._derive_keys(session.session_key)
    expected = hmac_sha256(mac_key, canonical_json({
        'header': header, 'iv': packet['iv'], 'ciphertext': packet['ciphertext']}))
    if not constant_time_equal(mac, expected):
        raise ValueError('Invalid message MAC')
    decryptor = Cipher(algorithms.AES(enc_key), modes.CBC(iv)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    plaintext = unpadder.update(padded) + unpadder.finalize()
    business = json.loads(plaintext.decode('utf-8'), parse_constant=_reject_constant)
    if not isinstance(business, dict):
        raise ValueError('Business payload must be an object')
    if business.get('device_id', device_id) != device_id:
        raise ValueError('Envelope/business device mismatch')
    business['device_id'] = device_id
    business.setdefault('request_id', request_id)
    business.setdefault('timestamp', timestamp)
    if header.get('unlock_token'):
        business['unlock_token'] = header['unlock_token']
    claim_message(session, request_id, nonce, timestamp + MAX_CLOCK_SKEW_SECONDS)
    return business


def _decrypt_v3(packet):
    header = packet['header']
    session_id = _text(header.get('session_id'), 'session_id', 32)
    request_id = _text(header.get('request_id'), 'request_id', 64)
    nonce = _text(header.get('nonce'), 'nonce', 64)
    timestamp = header.get('timestamp')
    if type(timestamp) is not int or abs(time.time() - timestamp) > MAX_CLOCK_SKEW_SECONDS:
        raise ValueError('Invalid or expired message timestamp')
    session = load_session(session_id)
    if session.protocol_version != VERSION:
        raise ValueError('Session protocol mismatch')
    plaintext = Envelope.open(session, packet, endpoint=request.path, method=request.method)
    business = json.loads(plaintext.decode('utf-8'), parse_constant=_reject_constant)
    if not isinstance(business, dict) or business.get('device_id', session.device_id) != session.device_id:
        raise ValueError('Invalid business device')
    business['device_id'] = session.device_id
    business.setdefault('request_id', request_id)
    business.setdefault('timestamp', timestamp)
    if header.get('unlock_token'):
        business['unlock_token'] = header['unlock_token']
    claim_message(session, request_id, nonce, timestamp + MAX_CLOCK_SKEW_SECONDS)
    return business


def _decrypt_legacy(packet):
    # Loaded only for an explicitly enabled historical upload. Modern startup needs no PEM file.
    from .AesCBCalgorithm import AesDecrypt
    from .ECCalgorithm import decrypt_aes_key_ecc
    with PRIVATE_KEY_PATH.open('rb') as file:
        private_key = serialization.load_pem_private_key(file.read(), password=None)
    key = decrypt_aes_key_ecc(base64.b64decode(packet['enc_key'], validate=True), private_key)
    if not key:
        raise ValueError('Invalid legacy key')
    business = json.loads(AesDecrypt(packet['payload'], key).decode('utf-8'), parse_constant=_reject_constant)
    if not isinstance(business, dict):
        raise ValueError('Business payload must be an object')
    return business


def decrypt_secure_payload(packet, *, allow_legacy=False):
    try:
        if not isinstance(packet, dict):
            raise ValueError('Secure packet must be an object')
        header = packet.get('header')
        if isinstance(header, dict) and header.get('version') == VERSION:
            return _decrypt_v3(packet)
        if isinstance(header, dict) and header.get('version') == PROTOCOL_VERSION:
            if not current_app.config['ALLOW_PROTOCOL_V2']:
                raise SecurePayloadError('Protocol v2 disabled', 'SECURE_PROTOCOL_REQUIRED', 401)
            return _decrypt_v2(packet)
        # A malformed or unsupported modern header must never be interpreted as a legacy packet.
        if 'header' not in packet and allow_legacy and current_app.config['ALLOW_LEGACY_SECURE_UPLOAD']:
            return _decrypt_legacy(packet)
        raise SecurePayloadError('Supported encrypted payload required', 'SECURE_PROTOCOL_REQUIRED', 401)
    except SecurePayloadError:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError, InvalidTag) as exc:
        raise SecurePayloadError('Invalid encrypted payload') from exc
