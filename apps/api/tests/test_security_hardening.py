"""Regressions for credential-at-rest, cross-request OTP replay and browser sessions."""
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import pyotp
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import test_auth_flow as fixtures
from app import create_app, db
from app.models import MFACredential, User


class SecurityHardeningTests(unittest.TestCase):
    setUp = fixtures.AuthFlowTests.setUp
    tearDown = fixtures.AuthFlowTests.tearDown
    post = fixtures.AuthFlowTests.post
    concurrent = fixtures.AuthFlowTests.concurrent

    def prelogin(self):
        result = self.post('/api/login/pre', {'username': 'alice', 'password': 'password'}, False)
        self.assertEqual(result.status_code, 200)
        return result.json['pre_token']

    def test_raw_database_has_authenticated_ciphertext_and_domain_reads_plaintext(self):
        with self.app.app_context():
            raw = db.session.execute(text("SELECT credential_data FROM mfa_credentials WHERE credential_type='totp'")).scalar_one()
            self.assertTrue(raw.startswith('enc:v1:'))
            self.assertNotIn(self.secret, raw)
            self.assertEqual(MFACredential.query.filter_by(credential_type='totp').one().credential_data, self.secret)

    def test_offline_migration_encrypts_legacy_values_and_is_idempotent(self):
        from app.schema import upgrade_schema
        with self.app.app_context():
            db.session.execute(text("UPDATE mfa_credentials SET credential_data=:secret WHERE credential_type='totp'"), {'secret': self.secret})
            db.session.commit()
            upgrade_schema()
            first = db.session.execute(text("SELECT credential_data FROM mfa_credentials WHERE credential_type='totp'")).scalar_one()
            upgrade_schema()
            second = db.session.execute(text("SELECT credential_data FROM mfa_credentials WHERE credential_type='totp'")).scalar_one()
            self.assertTrue(first.startswith('enc:v1:'))
            self.assertEqual(first, second)

    def test_wrong_storage_key_fails_closed_without_exposing_secret(self):
        old = self.app.config['SECRET_KEY']
        self.app.config['SECRET_KEY'] = 'different-storage-key-' + 'x' * 32
        try:
            result = self.client.get('/api/mfa/status', headers=self.headers)
            self.assertEqual(result.status_code, 503)
            self.assertNotIn(self.secret, result.get_data(as_text=True))
        finally:
            self.app.config['SECRET_KEY'] = old

    def test_same_otp_cannot_complete_distinct_login_challenges(self):
        tokens = [self.prelogin(), self.prelogin()]
        code = pyotp.TOTP(self.secret).now()
        results = [self.post('/api/login/mfa/verify', {'pre_token': token, 'code': code}, False).status_code for token in tokens]
        self.assertEqual(results, [200, 401])

    def test_concurrent_distinct_challenges_only_accept_one_otp(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        tokens = [self.prelogin(), self.prelogin()]
        barrier = Barrier(2)
        code = pyotp.TOTP(self.secret).now()
        def attempt(token):
            barrier.wait()
            with self.app.test_client() as client:
                return client.post('/api/login/mfa/verify', json={'pre_token': token, 'code': code}).status_code
        with ThreadPoolExecutor(2) as executor:
            results = list(executor.map(attempt, tokens))
        self.assertEqual(sorted(results), [200, 401])

    def test_otp_is_shared_across_routes_and_next_step_works(self):
        now = time.time()
        with patch('app.authenticators.time.time', return_value=now):
            code = pyotp.TOTP(self.secret).at(now)
            self.assertEqual(self.post('/api/login/mfa/verify', {'pre_token': self.prelogin(), 'code': code}, False).status_code, 200)
            self.assertEqual(self.post('/api/mfa/verify/totp', {'code': code}).status_code, 401)
            next_code = pyotp.TOTP(self.secret).at(now + 30)
            self.assertEqual(self.post('/api/mfa/verify/totp', {'code': next_code}).status_code, 200)
            self.assertEqual(self.post('/api/mfa/verify/totp', {'code': next_code}).status_code, 401)

    def test_browser_cookie_is_httponly_csrf_protected_and_logout_survives_restart(self):
        token = self.prelogin()
        result = self.client.post('/api/login/mfa/verify', json={
            'pre_token': token, 'code': pyotp.TOTP(self.secret).now()}, headers={'X-SmartLock-Session': 'browser'})
        self.assertEqual(result.status_code, 200)
        self.assertNotIn('access_token', result.json)
        self.assertTrue(any('HttpOnly' in header and 'SameSite=Strict' in header for header in result.headers.getlist('Set-Cookie')))
        cookie = self.client.get_cookie('smartlock_access', path='/api').value
        csrf = self.client.get_cookie('smartlock_csrf').value
        self.assertEqual(self.client.get('/api/account/session').status_code, 200)
        self.assertEqual(self.client.post('/api/logout', json={}).status_code, 401)
        self.assertEqual(self.client.post('/api/logout', json={}, headers={'X-CSRF-TOKEN': 'wrong'}).status_code, 401)
        self.assertEqual(self.client.post('/api/logout', json={}, headers={'X-CSRF-TOKEN': csrf}).status_code, 200)
        self.assertEqual(self.client.get('/api/account/session').status_code, 401)
        restarted = create_app(dict(self.app.config, AUTO_INIT_DB=False))
        other = restarted.test_client()
        other.set_cookie('smartlock_access', cookie, path='/api')
        self.assertEqual(other.get('/api/account/session').status_code, 401)
        with restarted.app_context():
            db.session.remove()
            db.engine.dispose()

    def test_new_passwords_use_scrypt_and_existing_bcrypt_is_upgraded(self):
        with self.app.app_context():
            self.assertTrue(db.session.get(User, self.uid).password_hash.startswith('$2'))
        self.prelogin()
        with self.app.app_context():
            self.assertTrue(db.session.get(User, self.uid).password_hash.startswith('scrypt:131072:8:1$'))

    def test_production_rejects_protocol_downgrade_and_unsafe_browser_flags(self):
        config = dict(self.app.config, TESTING=False, AUTO_INIT_DB=False,
                      DEPLOYMENT_ENV='production', ALLOW_DEMO_DEVICES=False,
                      ALLOW_PROTOCOL_V2=False, DEVICE_DISPATCH_REQUIRED=True,
                      FACE_PAD_REQUIRED=True, RATE_LIMIT_ENABLED=True,
                      JWT_COOKIE_SECURE=True, SECRET_KEY='s' * 48)
        for override in ({'ALLOW_PROTOCOL_V2': True}, {'JWT_COOKIE_SECURE': False},
                         {'JWT_COOKIE_CSRF_PROTECT': False}, {'JWT_COOKIE_SAMESITE': 'None'}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                create_app(dict(config, **override))

    def test_media_ciphertext_is_randomized_and_bound_to_asset_and_device(self):
        from app.media_storage import protect, unprotect
        from app.credential_storage import CredentialStorageError
        with self.app.app_context():
            content = b'private-image-fixture'
            first = protect(content, 'asset.jpg', 'door_a')
            second = protect(content, 'asset.jpg', 'door_a')
            self.assertNotEqual(first, second)
            self.assertNotIn(content, first)
            self.assertEqual(unprotect(first, 'asset.jpg', 'door_a'), content)
            for name, device, value in [('other.jpg', 'door_a', first),
                                         ('asset.jpg', 'door_b', first),
                                         ('asset.jpg', 'door_a', first[:-1] + bytes([first[-1] ^ 1]))]:
                with self.subTest(name=name, device=device), self.assertRaises(CredentialStorageError):
                    unprotect(value, name, device)

    def test_media_migration_preserves_bytes_and_is_idempotent(self):
        from app.models import MediaAsset
        from app.media_storage import migrate_media, unprotect, MAGIC
        with self.app.app_context():
            root = Path(self.app.config['UPLOAD_FOLDER'])
            root.mkdir(parents=True)
            path = root / ('a' * 32 + '.jpg')
            raw = b'legacy-private-image-fixture'
            path.write_bytes(raw)
            db.session.add(MediaAsset(filename=path.name, device_id='door_a'))
            db.session.commit()
            migrate_media()
            first = path.read_bytes()
            self.assertTrue(first.startswith(MAGIC))
            self.assertEqual(unprotect(first, path.name, 'door_a'), raw)
            migrate_media()
            self.assertEqual(path.read_bytes(), first)

    def test_smtp_explicitly_verifies_server_certificate_and_hostname(self):
        import ssl
        from types import SimpleNamespace
        from app.notifications import send_alarm
        with self.app.app_context(), patch('app.notifications.smtplib.SMTP_SSL') as smtp:
            send_alarm(SimpleNamespace(id=1, alarm_type='fixture', timestamp='fixture', message='fixture'))
            context = smtp.call_args.kwargs['context']
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
            self.assertTrue(context.check_hostname)

    def test_production_device_origin_requires_tls_outside_loopback(self):
        from app.provisioning import validate_service_url
        with self.app.app_context():
            self.app.config['DEPLOYMENT_ENV'] = 'production'
            self.assertEqual(validate_service_url('https://192.168.1.10:5443'), 'https://192.168.1.10:5443')
            with self.assertRaises(ValueError):
                validate_service_url('http://192.168.1.10:5000')

    def test_authenticator_removal_requires_fresh_otp_and_revokes_login(self):
        self.assertEqual(self.post('/api/mfa/unbind/totp', {}).status_code, 400)
        code = pyotp.TOTP(self.secret).now()
        self.assertEqual(self.post('/api/mfa/unbind/totp', {'code': code}).status_code, 200)
        self.assertEqual(self.client.get('/api/mfa/status', headers=self.headers).status_code, 401)


if __name__ == '__main__':
    unittest.main()
