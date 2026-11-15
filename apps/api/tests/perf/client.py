"""Shared MFA client used only by explicitly provisioned performance accounts."""
import base64
import hashlib
import os
from pathlib import Path
import sys

import pyotp

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.routes.security_protocol import SecureEnvelope, Spake2Client


def test_totp_secret(username):
    seed = os.environ.get('PERF_TOTP_SEED', 'local-perf-only-change-me')
    return base64.b32encode(hashlib.sha256((seed + ':' + username).encode()).digest()[:20]).decode()


def login_mfa(client, host, username, password, secret=None):
    response = client.post(host + '/api/login/pre', json={'username': username, 'password': password}, timeout=15)
    response.raise_for_status()
    challenge = response.json()
    if challenge['totp_bound']:
        endpoint = '/api/login/mfa/verify'
        secret = secret or test_totp_secret(username)
    else:
        endpoint = '/api/login/mfa/bind'
        secret = challenge['secret']
    response = client.post(host + endpoint, json={
        'pre_token': challenge['pre_token'], 'code': pyotp.TOTP(secret).now()}, timeout=15)
    response.raise_for_status()
    return response.json()['access_token']


def send_face_result(client, host, challenge, username, device_id):
    spake = Spake2Client(device_id, os.getenv('SMART_LOCK_DEVICE_PASSWORD', 'ChangeMe-Spake2-Device-Password'))
    state, start = spake.begin()
    response = client.post(host + '/api/security/spake2/start', json=start, timeout=15)
    response.raise_for_status()
    session = spake.finish(state, response.json())
    packet = SecureEnvelope.seal(session, {
        'device_id': device_id, 'request_id': challenge['request_id'],
        'session_nonce': challenge['nonce'], 'face_user_id': username, 'similarity_score': .95,
    })
    response = client.post(host + '/api/mfa/open-door/face-result', json=packet, timeout=15)
    response.raise_for_status()
    return response
