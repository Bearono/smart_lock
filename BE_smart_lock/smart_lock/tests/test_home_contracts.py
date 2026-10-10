"""Data contracts and versioned security boundaries for the home experience."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import time
import unittest
from unittest.mock import patch, Mock
import requests
from flask_jwt_extended import create_access_token
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app, db
from app.models import User, Device, AccessLog, MediaAsset, MFACredential, SecureMessageReceipt
from smartlock_protocol.v3 import Client, Envelope, Session, VERSION


class HomeContractsTests(unittest.TestCase):
    def test_handshake_rejects_non_object_json(self):
        for endpoint in ('start', 'confirm'):
            for body in ([1], 'invalid', 12, True):
                with self.subTest(endpoint=endpoint, body=body):
                    self.assertEqual(self.client.post('/api/security/spake2/'+endpoint, json=body).status_code, 400)

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.app = create_app({'TESTING': True, 'ALLOW_DEMO_DEVICES': True,
            'RATE_LIMIT_ENABLED': False, 'SECRET_KEY': 's'*48, 'JWT_SECRET_KEY': 'j'*48,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + (Path(self.tmp.name)/'test.db').as_posix(),
            'UPLOAD_FOLDER': str(Path(self.tmp.name)/'captures')})
        self.client = self.app.test_client()
        self.apps = [self.app]
        with self.app.app_context():
            db.session.add_all([User(username='operator', role='admin', status='approved', password_hash='unused'),
                                User(username='member', role='user', status='approved', password_hash='unused'),
                                Device(device_id='test_device')])
            db.session.commit()
            for user in User.query.all():
                db.session.add(MFACredential(user_id=user.id, credential_type='totp', credential_data='test', is_active=True))
            db.session.commit()
            self.headers = {name: {'Authorization': 'Bearer '+create_access_token(identity=name, additional_claims={'mfa': True})} for name in ('operator', 'member')}

    def tearDown(self):
        for app in self.apps:
            with app.app_context():
                db.session.remove()
                db.engine.dispose()
        self.tmp.cleanup()

    def provision_camera(self):
        from app.models import DeviceProvisioning
        from app.security_store import _cipher
        with self.app.app_context():
            db.session.add(DeviceProvisioning(device_id='test_device', enabled=True,
                service_url='https://camera.invalid',
                encrypted_password=_cipher().encrypt(b'independent-device-secret-32-bytes')))
            db.session.commit()

    def test_capture_requires_login_access_and_provisioning(self):
        with patch('app.routes.video.requests.post') as dispatch:
            self.assertEqual(self.client.post('/api/video/capture', json={'device_id':'test_device'}).status_code, 401)
            self.assertEqual(self.client.post('/api/video/capture', json={'device_id':'test_device'}, headers=self.headers['member']).status_code, 403)
            self.assertEqual(self.client.post('/api/video/capture', json={'device_id':'test_device'}, headers=self.headers['operator']).status_code, 503)
            self.assertEqual(self.client.post('/api/video/capture', json=[], headers=self.headers['operator']).status_code, 400)
            dispatch.assert_not_called()

    def test_capture_confirms_new_device_scoped_media_and_signs_command(self):
        self.provision_camera()
        filename='b'*32+'.jpg'
        def upload(*args, **kwargs):
            with self.app.app_context():
                db.session.add(MediaAsset(filename=filename,device_id='test_device'))
                db.session.commit()
            return Mock(status_code=200,json=lambda:{'status':'image_sent','info':{'snapshot':'/api/media/'+filename}})
        with patch('app.routes.video.requests.post',side_effect=upload) as dispatch:
            result=self.client.post('/api/video/capture',json={'device_id':'test_device'},headers=self.headers['operator'])
            self.assertEqual(result.status_code,200,result.json)
            self.assertEqual(result.json['snapshot'],'/api/media/'+filename)
            self.assertIsNone(result.json['captured_at'])
            self.assertTrue(result.json['received_at'])
            self.assertEqual(dispatch.call_args.args[0],'https://camera.invalid/capture_and_send')
            self.assertFalse(dispatch.call_args.kwargs['allow_redirects'])
            self.assertEqual(len(dispatch.call_args.kwargs['headers']['X-Command-Signature']),64)
        with self.app.app_context():
            self.assertEqual(AccessLog.query.one().action,'SNAPSHOT_CAPTURE')

    def test_capture_rejects_missing_foreign_and_old_receipts(self):
        self.provision_camera()
        with self.app.app_context():
            db.session.add_all([MediaAsset(filename='old.jpg',device_id='test_device'),
                MediaAsset(filename='foreign.jpg',device_id='other_device')])
            db.session.commit()
        for filename in ('missing.jpg','foreign.jpg','old.jpg'):
            reply=Mock(status_code=200,json=lambda:{'status':'image_sent','info':{'snapshot':'/api/media/'+filename}})
            with patch('app.routes.video.requests.post',return_value=reply):
                result=self.client.post('/api/video/capture',json={'device_id':'test_device'},headers=self.headers['operator'])
                self.assertEqual(result.status_code,502)
        with self.app.app_context():
            self.assertEqual(AccessLog.query.count(),0)

    def test_capture_timeout_and_invalid_reply_do_not_retry(self):
        self.provision_camera()
        for side_effect,reply,status in ((requests.Timeout(),None,504),(None,Mock(status_code=302),502),
                (None,Mock(status_code=200,json=lambda:[]),502)):
            with patch('app.routes.video.requests.post',side_effect=side_effect,return_value=reply) as dispatch:
                result=self.client.post('/api/video/capture',json={'device_id':'test_device'},headers=self.headers['operator'])
                self.assertEqual(result.status_code,status)
                self.assertEqual(dispatch.call_count,1)

    def test_capture_rate_limit_blocks_device_dispatch(self):
        self.provision_camera()
        self.app.config['RATE_LIMIT_ENABLED']=True
        with patch('app.routes.video.admit',return_value=(False,20)), patch('app.routes.video.requests.post') as dispatch:
            result=self.client.post('/api/video/capture',json={'device_id':'test_device'},headers=self.headers['operator'])
            self.assertEqual(result.status_code,429)
            self.assertEqual(result.headers['Retry-After'],'20')
            dispatch.assert_not_called()

    def session(self, confirm=True):
        client = Client('test_device', 'ChangeMe-Spake2-Device-Password')
        state, start = client.begin()
        reply = self.client.post('/api/security/spake2/start', json=start)
        self.assertEqual(reply.status_code, 200, reply.json)
        session = client.finish(state, reply.json)
        if confirm:
            result = self.client.post('/api/security/spake2/confirm', json=client.confirmation(session))
            self.assertEqual(result.status_code, 200, result.json)
            client.confirm(session, result.json)
        return client, session

    def packet(self, session):
        return Envelope.seal(session, {'lock_status': 'LOCKED'}, endpoint='/api/device/heartbeat')

    def test_name_is_persistent_authorized_and_audited(self):
        url = '/api/admin/devices/test_device/name'
        self.assertEqual(self.client.put(url, json={'display_name': '入户门'}, headers=self.headers['member']).status_code, 403)
        result = self.client.put(url, json={'display_name': '入户门'}, headers=self.headers['operator'])
        self.assertEqual(result.json['display_name'], '入户门')
        self.assertEqual(self.client.get('/api/device/status', headers=self.headers['operator']).json[0]['display_name'], '入户门')
        with self.app.app_context():
            self.assertEqual(AccessLog.query.one().device_id, 'test_device')
        self.assertEqual(self.client.put(url, json={'display_name': 'x'*61}, headers=self.headers['operator']).status_code, 400)

    def test_snapshot_is_receipt_not_capture_time(self):
        with self.app.app_context():
            db.session.add(MediaAsset(filename='a'*32+'.jpg', device_id='test_device'))
            db.session.commit()
        result = self.client.get('/api/video/latest?device_id=test_device', headers=self.headers['operator']).json
        self.assertIsNone(result['captured_at'])
        self.assertTrue(result['received_at'])

    def test_history_filter_is_scoped_and_checks_device_access(self):
        with self.app.app_context():
            db.session.add(Device(device_id='other_device'))
            db.session.add_all([
                AccessLog(username='operator', action='LOCK', device_id='test_device'),
                AccessLog(username='operator', action='UNLOCK', device_id='other_device'),
                AccessLog(username='operator', action='LOCK', device_id=None),
            ])
            db.session.commit()
        result = self.client.get('/api/lock/history?device_id=test_device', headers=self.headers['operator'])
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json['total'], 1)
        self.assertEqual(result.json['data'][0]['device_id'], 'test_device')
        denied = self.client.get('/api/lock/history?device_id=test_device', headers=self.headers['member'])
        self.assertEqual(denied.status_code, 403)

    def test_evidence_is_admin_only_and_has_no_secret(self):
        endpoint = '/api/admin/security/evidence'
        self.assertEqual(self.client.get(endpoint, headers=self.headers['member']).status_code, 403)
        result = self.client.get(endpoint, headers=self.headers['operator'])
        self.assertEqual(result.json['protocol']['version'], VERSION)
        self.assertNotIn('session_key', result.get_data(as_text=True))

    def test_gcm_replay_and_restart(self):
        _, session = self.session()
        packet = self.packet(session)
        self.assertEqual(self.client.post('/api/device/heartbeat', json=packet).status_code, 200)
        with self.app.app_context():
            self.assertEqual(SecureMessageReceipt.query.one().expires_at, session.expires_at)
        app = create_app(dict(self.app.config))
        self.apps.append(app)
        restarted = app.test_client()
        self.assertEqual(restarted.post('/api/device/heartbeat', json=packet).json['code'], 'SECURE_MESSAGE_REPLAY')

    def test_tamper_cross_endpoint_direction_and_downgrade(self):
        _, session = self.session()
        for mutate in ('ciphertext', 'endpoint', 'direction', 'device_id', 'version', 'timestamp'):
            packet = self.packet(session)
            if mutate == 'ciphertext':
                packet[mutate] = 'AAAA'
            else:
                packet['header'][mutate] = 0 if mutate == 'timestamp' else 'tampered'
            self.assertGreaterEqual(self.client.post('/api/device/heartbeat', json=packet).status_code, 400)
        packet = self.packet(session)
        self.assertEqual(self.client.post('/api/lock/ack', json=packet).status_code, 400)
        with self.app.app_context():
            self.assertEqual(Device.query.one().reported_status, 'UNKNOWN')

    def test_pending_session_cannot_execute(self):
        client, session = self.session(False)
        with self.assertRaises(ValueError):
            self.packet(session)
        session.confirmed = True  # Malicious client cannot activate the server record.
        packet = self.packet(session)
        self.assertEqual(self.client.post('/api/device/heartbeat', json=packet).status_code, 401)
        invalid = client.confirmation(session)
        invalid['proof'] = 'AAAA'
        self.assertEqual(self.client.post('/api/security/spake2/confirm', json=invalid).status_code, 400)

    def test_nonce_uniqueness_under_concurrency(self):
        session = Session('s', 'd', b'k'*32, time.time()+300, confirmed=True)
        with ThreadPoolExecutor(max_workers=8) as pool:
            packets = list(pool.map(lambda _: Envelope.seal(session, {}, endpoint='/api/device/heartbeat'), range(1000)))
        self.assertEqual(len({item['header']['nonce'] for item in packets}), 1000)
        session.counter = 2 ** 32
        with self.assertRaises(ValueError):
            Envelope.seal(session, {}, endpoint='/api/device/heartbeat')

    def test_client_rejects_handshake_downgrade(self):
        client = Client('test_device', 'password')
        state, _ = client.begin()
        with self.assertRaises(ValueError):
            client.finish(state, {'version': 'SL-SEC-v2'})
        with self.assertRaises(ValueError):
            client.finish(state, [])

    def test_malformed_confirmation_and_extra_handshake_data_are_rejected(self):
        for session_id in (None, [], {}, True, 'x'*33):
            self.assertEqual(self.client.post('/api/security/spake2/confirm', json={'session_id': session_id, 'proof': 'a'*44}).status_code, 400)
        client = Client('test_device', 'password')
        _, message = client.begin()
        message['unbounded_context'] = 'unexpected'
        self.assertEqual(self.client.post('/api/security/spake2/start', json=message).status_code, 400)

    def test_v2_can_be_explicitly_disabled(self):
        from smartlock_protocol.v2 import Spake2Client
        self.app.config['ALLOW_PROTOCOL_V2'] = False
        _, start = Spake2Client('test_device', 'password').begin()
        self.assertEqual(self.client.post('/api/security/spake2/start', json=start).status_code, 400)
        _, session = self.session()
        self.assertEqual(self.client.post('/api/device/heartbeat', json=self.packet(session)).status_code, 200)

    def test_timezone_is_declared_not_guessed(self):
        from datetime import datetime
        from app.time_contract import timestamp
        with self.app.app_context():
            self.app.config['SERVER_TIMEZONE'] = None
            self.assertEqual(timestamp(datetime(2026, 10, 8, 12)), '2026-10-08T12:00:00')
            self.app.config['SERVER_TIMEZONE'] = 'UTC'
            self.assertEqual(timestamp(datetime(2026, 10, 8, 12)), '2026-10-08T12:00:00+00:00')

    def test_report_loader_returns_only_allowlisted_metadata(self):
        import json
        path = Path(self.tmp.name)/'report.json'
        self.app.config['SECURITY_REPORT_PATH'] = str(path)
        fields = dict(created_at='2026-10-08T00:00:00Z', scope='software', git_sha='a'*40,
                      source_digest='b'*64, environment='isolated', passed=True,
                      checks=[{'name': 'test', 'exit_code': 0}], secret='must not appear')
        path.write_text(json.dumps(fields))
        result = self.client.get('/api/admin/security/evidence', headers=self.headers['operator'])
        self.assertEqual(result.json['verification']['checks'][0]['exit_code'], 0)
        self.assertNotIn('must not appear', result.get_data(as_text=True))
        path.write_text('{broken')
        self.assertIsNone(self.client.get('/api/admin/security/evidence', headers=self.headers['operator']).json['verification'])
