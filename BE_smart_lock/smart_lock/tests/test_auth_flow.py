"""Isolated regression suite: real Flask routes, SQLite transactions and SPAKE2 envelopes.

Run from smart_lock: python -m unittest discover -s tests -p 'test_*.py' -v
No live devices, existing databases, or SMTP calls are used.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
import sys
import unittest
from unittest.mock import patch

import pyotp
from flask_jwt_extended import create_access_token

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app, db, bcrypt
from app.models import AuthSession, Device, GuestPass, MFACredential, UnlockToken, User
from app.routes.mfa import DeviceUnavailable
from app.routes.security_protocol import SecureEnvelope, Spake2Client


class AuthFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.app = create_app({
            'TESTING': True, 'BCRYPT_LOG_ROUNDS': 4,
            'JWT_SECRET_KEY': 'isolated-regression-test-key-32-bytes',
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + (Path(self.tmp.name) / 'test.db').as_posix(),
            'UPLOAD_FOLDER': str(Path(self.tmp.name) / 'captures'),
            'DEVICE_DISPATCH_REQUIRED': False,
        })
        self.client = self.app.test_client()
        self.secret = pyotp.random_base32()
        with self.app.app_context():
            user = User(username='alice', status='approved',
                        password_hash=bcrypt.generate_password_hash('password').decode())
            db.session.add(user)
            db.session.flush()
            self.uid = user.id
            db.session.add(MFACredential(user_id=user.id, credential_type='totp',
                                        credential_data=self.secret, is_active=True))
            for device_id in ('door_a', 'door_b'):
                db.session.add(MFACredential(user_id=user.id, credential_type='device',
                                            device_id=device_id, credential_data='', is_active=True))
                db.session.add(Device(device_id=device_id))
            db.session.commit()
            self.headers = {'Authorization': 'Bearer ' + create_access_token(
                identity='alice', additional_claims={'mfa': True})}
        self.dispatch = patch('app.routes.mfa._dispatch_face_challenge', side_effect=DeviceUnavailable('offline'))
        self.dispatch.start()
        self.policy = patch('app.routes.mfa.evaluate_mfa_policy', return_value=['device', 'face'])
        self.policy.start()

    def tearDown(self):
        self.policy.stop()
        self.dispatch.stop()
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.tmp.cleanup()

    def post(self, path, body, authenticated=True, client=None):
        return (client or self.client).post(path, json=body, headers=self.headers if authenticated else {})

    def challenge(self, device='door_a'):
        response = self.post('/api/mfa/open-door/request', {'device_id': device})
        self.assertEqual(response.status_code, 200, response.json)
        return response.json

    def packet(self, challenge, *, device='door_a', nonce=None, user='alice', score=.95, **extra):
        spake = Spake2Client(device, 'ChangeMe-Spake2-Device-Password')
        state, message = spake.begin()
        reply = self.post('/api/security/spake2/start', message, False)
        self.assertEqual(reply.status_code, 200, reply.json)
        session = spake.finish(state, reply.json)
        return SecureEnvelope.seal(session, dict(
            request_id=challenge['request_id'], device_id=device,
            session_nonce=challenge['nonce'] if nonce is None else nonce,
            face_user_id=user, similarity_score=score, **extra))

    def verified(self):
        challenge = self.challenge()
        response = self.post('/api/mfa/open-door/face-result', self.packet(challenge), False)
        self.assertEqual(response.status_code, 200, response.json)
        return challenge

    def issued(self):
        challenge = self.verified()
        response = self.post('/api/mfa/open-door/confirm', {'request_id': challenge['request_id']})
        self.assertEqual(response.status_code, 200, response.json)
        return response.json

    def concurrent(self, path, body, authenticated=True):
        barrier = Barrier(2)
        def submit():
            with self.app.test_client() as client:
                barrier.wait(timeout=10)
                response = self.post(path, body, authenticated, client)
                return response.status_code, response.json
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(lambda _: submit(), range(2)))

    def test_password_login_cannot_issue_token_and_totp_is_single_use(self):
        response = self.post('/api/login', {'username': 'alice', 'password': 'password'}, False)
        self.assertNotIn('access_token', response.json)
        body = {'pre_token': response.json['pre_token'], 'code': pyotp.TOTP(self.secret).now()}
        results = self.concurrent('/api/login/mfa/verify', body, False)
        self.assertEqual(sum(status == 200 for status, _ in results), 1, results)

    def test_wrong_totp_can_retry_but_is_bounded(self):
        pre = self.post('/api/login/pre', {'username': 'alice', 'password': 'password'}, False).json
        valid = {pyotp.TOTP(self.secret).at(datetime.now() + timedelta(seconds=i * 30)) for i in (-1, 0, 1)}
        wrong = next(str(i).zfill(6) for i in range(100) if str(i).zfill(6) not in valid)
        for attempt in range(5):
            res = self.post('/api/login/mfa/verify', {'pre_token': pre['pre_token'], 'code': wrong}, False)
            self.assertEqual(res.status_code, 401)
            self.assertEqual(res.json['restart_login'], attempt == 4)
        res = self.post('/api/login/mfa/verify', {'pre_token': pre['pre_token'], 'code': pyotp.TOTP(self.secret).now()}, False)
        self.assertEqual(res.status_code, 401)

    def test_first_login_binding_and_account_revocation(self):
        with self.app.app_context():
            MFACredential.query.filter_by(user_id=self.uid, credential_type='totp').update({'is_active': False})
            db.session.commit()
        pre = self.post('/api/login', {'username': 'alice', 'password': 'password'}, False).json
        body = {'pre_token': pre['pre_token'], 'code': pyotp.TOTP(pre['secret']).now()}
        res = self.post('/api/login/mfa/bind', body, False)
        self.assertEqual(res.status_code, 200, res.json)
        with self.app.app_context():
            db.session.get(User, self.uid).status = 'rejected'
            db.session.commit()
        self.assertEqual(self.post('/api/mfa/open-door/request', {'device_id': 'door_a'}).status_code, 401)

    def test_legacy_jwt_and_direct_unlock_rejected(self):
        with self.app.app_context():
            token = create_access_token(identity='alice')
        self.assertEqual(self.client.get('/api/mfa/status', headers={'Authorization': 'Bearer ' + token}).status_code, 401)
        self.assertEqual(self.post('/api/lock/control', {'action': 'UNLOCK', 'device_id': 'door_a'}).status_code, 403)
        self.assertEqual(self.post('/api/lock/control', {'action': 'LOCK', 'device_id': 'unknown'}).status_code, 403)

    def test_development_dispatch_requires_real_encrypted_result(self):
        challenge = self.challenge()
        self.assertEqual(challenge['device_dispatch']['status'], 'pending')
        self.assertEqual(self.post('/api/mfa/open-door/confirm', {'request_id': challenge['request_id']}).status_code, 401)
        self.assertEqual(self.post('/api/mfa/open-door/face-result', challenge, False).status_code, 401)

    def test_production_dispatch_and_device_rejection_fail_closed(self):
        self.app.config['DEVICE_DISPATCH_REQUIRED'] = True
        self.assertEqual(self.post('/api/mfa/open-door/request', {'device_id': 'door_a'}).status_code, 502)
        self.app.config['DEVICE_DISPATCH_REQUIRED'] = False
        with patch('app.routes.mfa._dispatch_face_challenge', side_effect=RuntimeError('face rejected')):
            self.assertEqual(self.post('/api/mfa/open-door/request', {'device_id': 'door_a'}).status_code, 502)

    def test_face_nonce_device_and_mac_validation(self):
        challenge = self.challenge()
        packet = self.packet(challenge, device='door_b')
        self.assertEqual(self.post('/api/mfa/open-door/face-result', packet, False).status_code, 403)
        packet = self.packet(challenge)
        packet['mac'] = 'AAAA'
        self.assertEqual(self.post('/api/mfa/open-door/face-result', packet, False).status_code, 400)
        response = self.post('/api/mfa/open-door/face-result', self.packet(challenge, nonce='wrong'), False)
        self.assertEqual(response.status_code, 401, response.json)
        with self.app.app_context():
            self.assertEqual(AuthSession.query.filter_by(request_id=challenge['request_id']).one().status, 'failed')

    def test_replayed_face_packet_and_expired_session(self):
        challenge = self.challenge()
        packet = self.packet(challenge)
        self.assertEqual(self.post('/api/mfa/open-door/face-result', packet, False).status_code, 200)
        self.assertEqual(self.post('/api/mfa/open-door/face-result', packet, False).status_code, 400)
        with self.app.app_context():
            AuthSession.query.filter_by(request_id=challenge['request_id']).one().expires_at = datetime.now() - timedelta(seconds=1)
            db.session.commit()
        self.assertEqual(self.post('/api/mfa/open-door/confirm', {'request_id': challenge['request_id']}).status_code, 410)
        other = self.challenge()
        with self.app.app_context():
            AuthSession.query.filter_by(request_id=other['request_id']).one().expires_at = datetime.now() - timedelta(seconds=1)
            db.session.commit()
        self.assertEqual(self.post('/api/mfa/open-door/face-result', self.packet(other), False).status_code, 410)

    def test_confirm_concurrency_issues_only_one_token(self):
        challenge = self.verified()
        results = self.concurrent('/api/mfa/open-door/confirm', {'request_id': challenge['request_id']})
        self.assertEqual(sum(status == 200 for status, _ in results), 1, results)
        with self.app.app_context():
            self.assertEqual(UnlockToken.query.count(), 1)
            self.assertEqual(Device.query.filter_by(device_id='door_a').one().status, 'LOCKED')

    def test_token_device_expiry_and_concurrent_consumption(self):
        credential = self.issued()
        self.assertEqual(self.post('/api/lock/unlock-token/verify', dict(credential, device_id='door_b'), False).status_code, 403)
        results = self.concurrent('/api/lock/unlock-token/verify', credential, False)
        self.assertEqual(sum(status == 200 for status, _ in results), 1, results)
        accepted = next(body for status, body in results if status == 200)
        self.assertTrue(accepted['command_accepted'])
        self.assertFalse(accepted['hardware_confirmed'])
        other = self.issued()
        with self.app.app_context():
            UnlockToken.query.filter_by(token=other['unlock_token']).one().expires_at = datetime.now() - timedelta(seconds=1)
            db.session.commit()
        self.assertEqual(self.post('/api/lock/unlock-token/verify', other, False).status_code, 401)

    def test_five_failures_lock_only_target_and_rebinding_does_not_reset(self):
        for _ in range(5):
            challenge = self.challenge('door_b')
            self.assertEqual(self.post('/api/mfa/open-door/face-result', self.packet(challenge, device='door_b', user='someone_else'), False).status_code, 401)
        self.assertEqual(self.post('/api/mfa/open-door/request', {'device_id': 'door_b'}).status_code, 423)
        self.post('/api/mfa/unbind/device', {'device_id': 'door_b'})
        self.post('/api/mfa/bind/device', {'device_id': 'door_b'})
        self.assertEqual(self.post('/api/mfa/open-door/request', {'device_id': 'door_b'}).status_code, 423)
        self.challenge('door_a')

    def test_unbinding_revokes_issued_token(self):
        credential = self.issued()
        self.post('/api/mfa/unbind/device', {'device_id': 'door_a'})
        self.assertNotEqual(self.post('/api/lock/unlock-token/verify', credential, False).status_code, 200)
        self.post('/api/mfa/bind/device', {'device_id': 'door_a'})
        self.assertNotEqual(self.post('/api/lock/unlock-token/verify', credential, False).status_code, 200)

    def test_legacy_duplicate_bindings_do_not_hide_lockout(self):
        with self.app.app_context():
            db.session.add(MFACredential(user_id=self.uid, credential_type='device',
                                        device_id='door_a', credential_data='', is_active=True, is_locked=True))
            db.session.commit()
        self.assertEqual(self.post('/api/mfa/open-door/request', {'device_id': 'door_a'}).status_code, 423)
        self.post('/api/mfa/unbind/device', {'device_id': 'door_a'})
        self.post('/api/mfa/bind/device', {'device_id': 'door_a'})
        self.assertEqual(self.post('/api/mfa/open-door/request', {'device_id': 'door_a'}).status_code, 423)

    def test_heartbeat_cannot_bypass_unlock_authorization(self):
        response = self.client.get('/api/device/status?device_id=door_a', headers=self.headers)
        self.assertFalse(response.json['is_online'])
        body = {'device_id': 'door_a', 'lock_status': 'UNLOCKED'}
        self.assertEqual(self.post('/api/device/heartbeat', body, False).status_code, 401)
        self.assertEqual(self.post('/api/lock/sync', body, False).status_code, 401)
        challenge = self.challenge()
        packet = self.packet(challenge, lock_status='UNLOCKED')
        response = self.post('/api/device/heartbeat', packet, False)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json['device']['reported_status'], 'UNLOCKED')
        self.assertEqual(response.json['device']['status'], 'LOCKED')

    def test_consumption_rolls_back_if_commit_fails(self):
        credential = self.issued()
        with patch.object(db.session, 'commit', side_effect=RuntimeError('storage failure')):
            with self.assertRaises(RuntimeError):
                self.post('/api/lock/unlock-token/verify', credential, False)
        with self.app.app_context():
            self.assertFalse(UnlockToken.query.filter_by(token=credential['unlock_token']).one().is_used)
            self.assertEqual(Device.query.filter_by(device_id='door_a').one().status, 'LOCKED')
        self.assertEqual(self.post('/api/lock/unlock-token/verify', credential, False).status_code, 200)

    def test_performance_client_runs_full_simulated_flow(self):
        import importlib.util
        import requests
        perf_dir = Path(__file__).parent / 'perf'
        sys.path.insert(0, str(perf_dir))
        from client import test_totp_secret
        spec = importlib.util.spec_from_file_location('measure_e2e', perf_dir / 'measure_e2e.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with self.app.app_context():
            MFACredential.query.filter_by(user_id=self.uid, credential_type='totp').one().credential_data = test_totp_secret('alice')
            db.session.commit()
        class Response:
            def __init__(self, response):
                self.response = response
            def json(self):
                return self.response.json
            def raise_for_status(self):
                if self.response.status_code >= 400:
                    raise requests.HTTPError(str(self.response.json))
        class Client:
            def post(_self, url, json, headers=None, timeout=None):
                return Response(self.client.post(url, json=json, headers=headers or {}))
        result = module.one_run(Client(), '', 'alice', 'password', 'door_a', simulate_face=True)
        self.assertGreater(result['total'], 0)
        with self.app.app_context():
            self.assertTrue(UnlockToken.query.one().is_used)

    def test_night_policy_persists_until_confirmation(self):
        with patch('app.routes.mfa.evaluate_mfa_policy', return_value=['device', 'face', 'totp']):
            challenge = self.verified()
        body = {'request_id': challenge['request_id']}
        self.assertEqual(self.post('/api/mfa/open-door/confirm', body).status_code, 400)
        body['totp_code'] = pyotp.TOTP(self.secret).now()
        self.assertEqual(self.post('/api/mfa/open-door/confirm', body).status_code, 200)

    def test_guest_budget_device_binding_and_revocation(self):
        response = self.post('/api/mfa/guest/create', {'device_id': 'door_a', 'guest_name': 'guest', 'max_uses': 1})
        self.assertEqual(response.status_code, 200, response.json)
        results = self.concurrent('/api/mfa/guest/verify', {'pass_code': response.json['pass_code']}, False)
        self.assertEqual(sum(status == 200 for status, _ in results), 1, results)
        credential = next(body for status, body in results if status == 200)
        self.assertEqual(credential['device_id'], 'door_a')
        with self.app.app_context():
            guest = GuestPass.query.one()
            self.assertEqual(guest.used_count, 1)
            guest_id = guest.id
        self.post('/api/mfa/guest/revoke/' + str(guest_id), {})
        self.assertEqual(self.post('/api/lock/unlock-token/verify', credential, False).status_code, 403)


if __name__ == '__main__':
    unittest.main()
