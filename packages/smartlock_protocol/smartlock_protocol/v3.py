"""Version 3: transcript confirmation and context-bound AES-256-GCM.

SPAKE2 remains the course baseline; its Python implementation is not constant time.
Each fresh session uses a fresh key and monotonic 96-bit nonces. Never persist/reuse
client keys across restarts. Server restarts retain replay receipts and session keys.
"""
from dataclasses import dataclass, field
from threading import Lock
import hashlib
import time
import uuid

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from .v2 import Spake2Client as BaselineClient
from .v2 import b64d, b64e, canonical_json, hkdf, hmac_sha256, constant_time_equal

VERSION = 'SL-SEC-v3'
MAX_SESSION_MESSAGES = 2 ** 32


def transcript(start, reply):
    return canonical_json({'start': start, 'reply': {key: reply[key] for key in
        ('version', 'session_id', 'server_pub', 'server_nonce', 'expires_at')}})


def derive_session_key(base_key, transcript_bytes):
    return hkdf(base_key, salt=hashlib.sha256(transcript_bytes).digest(), info=b'SL-SEC-v3/session')


def proof(key, transcript_bytes, direction):
    confirm_key = hkdf(key, salt=b'SL-SEC-v3', info=b'confirmation/' + direction.encode())
    return b64e(hmac_sha256(confirm_key, transcript_bytes))


def verify_proof(key, transcript_bytes, direction, candidate):
    return constant_time_equal(b64d(proof(key, transcript_bytes, direction)), b64d(candidate))


@dataclass
class Session:
    session_id: str
    device_id: str
    session_key: bytes
    expires_at: float
    transcript_bytes: bytes = b''
    confirmed: bool = False
    counter: int = 0
    lock: Lock = field(default_factory=Lock, repr=False)

    def nonce(self):
        with self.lock:
            if self.counter >= MAX_SESSION_MESSAGES:
                raise ValueError('Session nonce space exhausted')
            value = self.counter.to_bytes(12, 'big')
            self.counter += 1
            return value


class Client(BaselineClient):
    def begin(self):
        state, message = super().begin()
        message['version'] = VERSION
        state.start_message = dict(message)
        return state, message

    def finish(self, state, reply):
        if not isinstance(reply, dict) or reply.get('version') != VERSION:
            raise ValueError('Protocol downgrade rejected')
        # Verify the baseline server proof, then bind the complete versioned transcript.
        baseline = super().finish(state, dict(reply, version='SL-SEC-v2', challenge=reply['baseline_challenge']))
        context = transcript(state.start_message, reply)
        key = derive_session_key(baseline.session_key, context)
        if not verify_proof(key, context, 'server', reply['challenge']):
            raise ValueError('Invalid versioned handshake proof')
        return Session(baseline.session_id, baseline.device_id, key, baseline.expires_at, context)

    @staticmethod
    def confirmation(session):
        return {'version': VERSION, 'session_id': session.session_id,
                'proof': proof(session.session_key, session.transcript_bytes, 'client')}

    @staticmethod
    def confirm(session, reply):
        if not isinstance(reply, dict) or reply.get('version') != VERSION or not verify_proof(session.session_key, session.transcript_bytes, 'confirmed', reply.get('proof')):
            raise ValueError('Invalid confirmation receipt')
        session.confirmed = True


def traffic_key(key, direction):
    return hkdf(key, salt=b'SL-SEC-v3', info=b'AES-256-GCM/' + direction.encode())


class Envelope:
    @staticmethod
    def seal(session, plaintext, *, endpoint, method='POST', unlock_token=None):
        if not session.confirmed or session.expires_at <= time.time():
            raise ValueError('Unconfirmed or expired session')
        nonce = session.nonce()
        header = {'version': VERSION, 'session_id': session.session_id, 'device_id': session.device_id,
                  'request_id': uuid.uuid4().hex, 'timestamp': int(time.time()), 'nonce': b64e(nonce),
                  'endpoint': endpoint, 'method': method, 'direction': 'device-to-server'}
        if unlock_token:
            header['unlock_token'] = unlock_token
        cipher = AESGCM(traffic_key(session.session_key, 'device-to-server')).encrypt(nonce, canonical_json(plaintext), canonical_json(header))
        return {'header': header, 'ciphertext': b64e(cipher)}

    @staticmethod
    def open(session, packet, *, endpoint, method='POST'):
        if not getattr(session, 'confirmed', False) or session.expires_at <= time.time():
            raise ValueError('Unconfirmed or expired session')
        header = packet['header']
        if (header.get('version') != VERSION or header.get('endpoint') != endpoint
                or header.get('method') != method or header.get('direction') != 'device-to-server'
                or header.get('device_id') != session.device_id or header.get('session_id') != session.session_id):
            raise ValueError('Message context mismatch')
        nonce = b64d(header['nonce'])
        if len(nonce) != 12:
            raise ValueError('Invalid GCM nonce')
        return AESGCM(traffic_key(session.session_key, 'device-to-server')).decrypt(nonce, b64d(packet['ciphertext']), canonical_json(header))
