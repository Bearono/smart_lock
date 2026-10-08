"""Exercise transport state across real processes, concurrency and device recovery."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
import importlib.util
import json
import subprocess
import sys
import time
import types
import unittest
from unittest.mock import patch

import requests

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parents[1]
sys.path.insert(0, str(BACKEND))
from app import create_app, db
from app.models import DeviceSecuritySession, SecureMessageReceipt
from app.routes.security_protocol import SecureEnvelope, Spake2Client, b64e, canonical_json, hmac_sha256


def load_device_transport():
    spec = importlib.util.spec_from_file_location('device_transport_under_test', ROOT / 'paspberry_pi/transmit.py')
    module = importlib.util.module_from_spec(spec)
    with patch.object(sys, 'path', [str(ROOT / 'paspberry_pi')] + sys.path):
        with patch.dict(sys.modules, {'cv2': types.ModuleType('cv2')}):
            spec.loader.exec_module(module)
    return module


class SecureTransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.config = {
            'TESTING': True, 'BCRYPT_LOG_ROUNDS': 4,
            'ALLOW_DEMO_DEVICES': True,
            'RATE_LIMIT_ENABLED': False,
            'SECRET_KEY': 'shared-test-storage-key',
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + (Path(self.tmp.name) / 'transport.db').as_posix(),
            'UPLOAD_FOLDER': str(Path(self.tmp.name) / 'captures'),
        }
        self.apps = []
        self.app = self.new_app()
        self.client = self.app.test_client()
        spake = Spake2Client('test_device', 'ChangeMe-Spake2-Device-Password')
        state, message = spake.begin()
        response = self.client.post('/api/security/spake2/start', json=message)
        self.assertEqual(response.status_code, 200, response.json)
        self.session = spake.finish(state, response.json)

    def new_app(self, **overrides):
        app = create_app(dict(self.config, **overrides))
        self.apps.append(app)
        return app

    def tearDown(self):
        for app in self.apps:
            with app.app_context():
                db.session.remove()
                db.engine.dispose()
        self.tmp.cleanup()

    def packet(self, **business):
        return SecureEnvelope.seal(self.session, dict(device_id='test_device', **business))

    def post(self, packet, client=None, endpoint='/api/secure/upload'):
        return (client or self.client).post(endpoint, json=packet)

    def resign(self, packet):
        _, mac_key = SecureEnvelope._derive_keys(self.session.session_key)
        packet['mac'] = b64e(hmac_sha256(mac_key, canonical_json({
            key: packet[key] for key in ('header', 'iv', 'ciphertext')})))
        return packet

    def test_session_keys_are_encrypted_and_shared_by_restarted_app(self):
        with self.app.app_context():
            record = db.session.get(DeviceSecuritySession, self.session.session_id)
            self.assertNotEqual(record.encrypted_key, self.session.session_key)
            self.assertNotIn(self.session.session_key, record.encrypted_key)
        packet = self.packet()
        other = self.new_app().test_client()
        self.assertEqual(self.post(packet, other).status_code, 200)
        response = self.post(packet)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json['code'], 'SECURE_MESSAGE_REPLAY')

    def test_two_processes_share_session_and_admit_packet_only_once(self):
        packet = self.packet()
        script = '''
import json, sys
from app import create_app, db
data = json.loads(sys.stdin.read())
app = create_app(data['config'])
response = app.test_client().post('/api/secure/upload', json=data['packet'])
print(json.dumps({'status': response.status_code, 'body': response.json}))
with app.app_context():
    db.session.remove()
    db.engine.dispose()
'''
        barrier = Barrier(2)
        def send():
            barrier.wait(timeout=10)
            result = subprocess.run([sys.executable, '-B', '-c', script], cwd=BACKEND,
                                    input=json.dumps({'config': self.config, 'packet': packet}),
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: send(), range(2)))
        self.assertEqual(sorted(result['status'] for result in results), [200, 400], results)
        with self.app.app_context():
            self.assertEqual(SecureMessageReceipt.query.count(), 1)

    def test_either_duplicate_nonce_or_request_id_is_rejected(self):
        first = self.packet()
        self.assertEqual(self.post(first).status_code, 200)
        for field in ('nonce', 'request_id'):
            second = self.packet()
            second['header'][field] = first['header'][field]
            response = self.post(self.resign(second))
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json['code'], 'SECURE_MESSAGE_REPLAY')

    def test_invalid_mac_does_not_burn_valid_packet(self):
        packet = self.packet()
        damaged = dict(packet, mac=b64e(b'x' * 32))
        self.assertEqual(self.post(damaged).status_code, 400)
        self.assertEqual(self.post(packet).status_code, 200)

    def test_expiry_cleanup_retains_unexpired_replay_protection(self):
        packet = self.packet()
        self.assertEqual(self.post(packet).status_code, 200)
        with self.app.app_context():
            db.session.add(SecureMessageReceipt(session_id='expired', request_id='old', nonce='old', expires_at=0))
            db.session.commit()
        self.assertEqual(self.post(self.packet()).status_code, 200)
        with self.app.app_context():
            self.assertIsNone(SecureMessageReceipt.query.filter_by(session_id='expired').first())
        self.assertEqual(self.post(packet).status_code, 400)

    def test_rotating_storage_key_requires_handshake_without_burning_packet(self):
        packet = self.packet()
        other = self.new_app(SECRET_KEY='rotated-key').test_client()
        response = self.post(packet, other)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json['code'], 'SECURITY_SESSION_INVALID')
        self.assertEqual(self.post(packet).status_code, 200)

    def test_expired_server_session_returns_recoverable_error(self):
        packet = self.packet()
        with self.app.app_context():
            db.session.get(DeviceSecuritySession, self.session.session_id).expires_at = time.time() - 1
            db.session.commit()
        response = self.post(packet)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json['code'], 'SECURITY_SESSION_INVALID')

    def test_malformed_fields_never_raise_server_error(self):
        for field, value in [('timestamp', True), ('timestamp', []), ('nonce', []),
                             ('nonce', b64e(b'short')), ('session_id', {}), ('device_id', 7)]:
            with self.subTest(field=field, value=value):
                packet = self.packet()
                packet['header'][field] = value
                self.assertEqual(self.post(packet).status_code, 400)
        for field, value in [('iv', None), ('iv', b64e(b'x')), ('ciphertext', []),
                             ('ciphertext', ''), ('mac', 'AAA!')]:
            packet = self.packet()
            packet[field] = value
            self.assertEqual(self.post(packet).status_code, 400)
        for timestamp in (None, 'yesterday', {}, True):
            spake = Spake2Client('test_device', 'password')
            _, message = spake.begin()
            message['timestamp'] = timestamp
            self.assertEqual(self.client.post('/api/security/spake2/start', json=message).status_code, 400)

    def test_modern_startup_and_upload_do_not_read_private_key(self):
        with patch('pathlib.Path.open', side_effect=AssertionError('PEM must not be loaded')):
            other = self.new_app().test_client()
            self.assertEqual(self.post(self.packet(), other).status_code, 200)
        self.assertEqual(self.post({'enc_key': 'x', 'payload': 'x'}).status_code, 401)
        other = self.new_app(ALLOW_LEGACY_SECURE_UPLOAD=True).test_client()
        with patch('app.routes.secure_payload._decrypt_legacy', side_effect=AssertionError('no downgrade')):
            self.assertEqual(self.post({'header': {'version': 'unknown'}, 'enc_key': 'x', 'payload': 'x'}, other).status_code, 401)

    def test_device_really_rehandshakes_after_server_loses_session(self):
        module = load_device_transport()
        transmitter = module.NetworkTransmitter('http://backend', device_id='test_device')
        calls = []
        def send(url, json, timeout, verify):
            self.assertTrue(verify)
            endpoint = url.removeprefix('http://backend')
            calls.append(endpoint)
            with self.app.test_client() as client:
                result = client.post(endpoint, json=json)
            response = requests.Response()
            response.status_code = result.status_code
            response._content = result.data
            return response
        with patch.object(module.requests, 'post', side_effect=send):
            first = transmitter.heartbeat('LOCKED')
            self.assertEqual(first['device']['reported_status'], 'LOCKED')
            old_session = transmitter.security_session.session_id
            with self.app.app_context():
                db.session.delete(db.session.get(DeviceSecuritySession, old_session))
                db.session.commit()
            second = transmitter.heartbeat('UNLOCKED')
            self.assertEqual(second['device']['reported_status'], 'UNLOCKED')
            self.assertNotEqual(old_session, transmitter.security_session.session_id)
        self.assertEqual(calls.count('/api/security/spake2/start'), 2)
        self.assertEqual(calls.count('/api/device/heartbeat'), 3)

    def test_oversized_request_rejected_before_processing(self):
        self.app.config['MAX_CONTENT_LENGTH'] = 1024
        self.assertEqual(self.post({'image': 'a' * 2048}).status_code, 413)


class DeviceRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Test the real device transport without importing camera/native dependencies.
        cls.module = load_device_transport()

    def setUp(self):
        self.transmitter = self.module.NetworkTransmitter('http://test-backend', device_id='device')
        from smartlock_protocol.v3 import Session
        self.session = Session('a' * 32, 'device', b'k' * 32, time.time() + 300, confirmed=True)

    def response(self, status, payload):
        response = requests.Response()
        response.status_code = status
        response._content = json.dumps(payload).encode()
        return response

    def test_only_session_invalid_retries_with_fresh_envelope(self):
        responses = [self.response(401, {'code': 'SECURITY_SESSION_INVALID'}), self.response(200, {'status': 'success'})]
        with patch.object(self.transmitter, '_ensure_secure_session', return_value=self.session) as handshake:
            with patch.object(self.module.requests, 'post', side_effect=responses) as post:
                result = self.transmitter._send_encrypted('/api/secure/upload', {'hello': 'world'})
        self.assertEqual(result['status'], 'success')
        self.assertEqual(handshake.call_count, 2)
        packets = [call.kwargs['json'] for call in post.call_args_list]
        self.assertNotEqual(packets[0]['header']['request_id'], packets[1]['header']['request_id'])
        self.assertNotEqual(packets[0]['header']['nonce'], packets[1]['header']['nonce'])

    def test_ambiguous_or_business_errors_never_retry_or_downgrade(self):
        for outcome in (requests.Timeout('timeout'), self.response(500, {'msg': 'storage error'}),
                        self.response(401, {'msg': 'Face verification failed'}),
                        self.response(400, {'code': 'SECURE_MESSAGE_REPLAY'}), self.response(200, [])):
            with self.subTest(outcome=str(outcome)):
                with patch.object(self.transmitter, '_ensure_secure_session', return_value=self.session):
                    with patch.object(self.module.requests, 'post', side_effect=[outcome]) as post:
                        result = self.transmitter._send_encrypted('/api/secure/upload', {})
                self.assertEqual(result['status'], 'error')
                self.assertGreaterEqual(result['http_status'], 400)
                self.assertEqual(post.call_count, 1)
                self.assertNotIn('enc_key', post.call_args.kwargs['json'])

    def test_recovery_stops_after_one_rehandshake(self):
        response = self.response(401, {'code': 'SECURITY_SESSION_INVALID'})
        with patch.object(self.transmitter, '_ensure_secure_session', return_value=self.session):
            with patch.object(self.module.requests, 'post', return_value=response) as post:
                result = self.transmitter._send_encrypted('/api/secure/upload', {})
        self.assertEqual(result['http_status'], 401)
        self.assertEqual(post.call_count, 2)


if __name__ == '__main__':
    unittest.main()
