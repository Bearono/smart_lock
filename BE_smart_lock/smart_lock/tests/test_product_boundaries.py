"""Delivery boundaries: explicit initialization, provisioning, isolation and recovery."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import base64
import hashlib
import hmac
import importlib.util
import json
import sys
import time
import types
import unittest
import zipfile

import pyotp
from flask import Flask
from flask_jwt_extended import create_access_token
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app, db, bcrypt
from app.models import DeviceGrant, DeviceProvisioning, MediaAsset, MFACredential, User
from app.routes.security_protocol import Spake2Client, SecureEnvelope
from app.rate_limit import admit
from app.models import DoorCommand
from app.door_commands import enqueue
from app.routes.security_protocol import SecureResponse


class ProductBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.config = {'TESTING': True, 'BCRYPT_LOG_ROUNDS': 4, 'SECRET_KEY': 's' * 48,
                       'JWT_SECRET_KEY': 'j' * 48, 'ALLOW_DEMO_DEVICES': False,
                       'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + (Path(self.tmp.name) / 'app.db').as_posix(),
                       'UPLOAD_FOLDER': str(Path(self.tmp.name) / 'captures')}
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        self.cli = self.app.test_cli_runner()
        with self.app.app_context():
            for name in ('alice', 'bob'):
                user = User(username=name, status='approved', role='user', password_hash=bcrypt.generate_password_hash('long-password').decode())
                db.session.add(user)
                db.session.flush()
                db.session.add(MFACredential(user_id=user.id, credential_type='totp', credential_data=pyotp.random_base32(), is_active=True))
            db.session.commit()
            self.headers = {name: {'Authorization': 'Bearer ' + create_access_token(identity=name, additional_claims={'mfa': True})} for name in ('alice', 'bob')}

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.tmp.cleanup()

    def provision(self, password='d' * 48):
        result = self.cli.invoke(args=['provision-device', '--device-id', 'door_a', '--service-url', 'http://device:5000', '--password', password])
        self.assertEqual(result.exit_code, 0, result.output + str(result.exception))
        return password

    def grant(self, name='alice', revoke=False):
        result = self.cli.invoke(args=['grant-device', '--username', name, '--device-id', 'door_a'] + (['--revoke'] if revoke else []))
        self.assertEqual(result.exit_code, 0, result.output)
        if not revoke:
            result = self.client.post('/api/mfa/bind/device', json={'device_id': 'door_a'}, headers=self.headers[name])
            self.assertEqual(result.status_code, 200)

    def handshake(self, password):
        spake = Spake2Client('door_a', password)
        state, message = spake.begin()
        result = self.client.post('/api/security/spake2/start', json=message)
        self.assertEqual(result.status_code, 200, result.json)
        return spake.finish(state, result.json)

    def test_startup_has_no_default_admin_and_cannot_promote_existing_username(self):
        with self.app.app_context():
            self.assertEqual(User.query.filter_by(role='admin').count(), 0)
        result = self.cli.invoke(args=['create-admin', '--username', 'alice', '--password', 'safe-admin-password'])
        self.assertNotEqual(result.exit_code, 0)
        result = self.cli.invoke(args=['create-admin', '--username', 'operator', '--password', 'safe-admin-password'])
        self.assertEqual(result.exit_code, 0, result.output)
        with self.app.app_context():
            self.assertEqual(User.query.filter_by(username='alice').one().role, 'user')
            self.assertEqual(User.query.filter_by(role='admin').count(), 1)

    def test_production_rejects_unsafe_flags_before_creating_database(self):
        base = dict(self.config, TESTING=False, DEPLOYMENT_ENV='production', AUTO_INIT_DB=False)
        for overrides in ({'SECRET_KEY': None}, {'JWT_SECRET_KEY': 'short'}, {'AUTO_INIT_DB': True},
                          {'ALLOW_DEMO_DEVICES': True}, {'ALLOW_LEGACY_SECURE_UPLOAD': True},
                          {'DEVICE_DISPATCH_REQUIRED': False}, {'CORS_ORIGINS': ['*']}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                create_app(dict(base, **overrides))
        app = create_app(dict(base, SQLALCHEMY_DATABASE_URI='sqlite:///' + (Path(self.tmp.name) / 'empty.db').as_posix()))
        self.assertEqual(app.test_client().get('/health/live').status_code, 200)
        self.assertEqual(app.test_client().get('/health/ready').status_code, 503)
        result = app.test_cli_runner().invoke(args=['init-db'])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(app.test_client().get('/health/ready').status_code, 200)
        with app.app_context():
            db.session.remove()
            db.engine.dispose()

    def test_unknown_device_rejected_and_rotating_secret_revokes_old_session(self):
        _, message = Spake2Client('door_a', 'demo').begin()
        self.assertEqual(self.client.post('/api/security/spake2/start', json=message).status_code, 403)
        password = self.provision()
        session = self.handshake(password)
        self.provision('e' * 48)
        packet = SecureEnvelope.seal(session, {'device_id': 'door_a'})
        result = self.client.post('/api/secure/upload', json=packet)
        self.assertEqual(result.status_code, 401)
        with self.app.app_context():
            self.assertNotIn(password.encode(), db.session.get(DeviceProvisioning, 'door_a').encrypted_password)

    def test_device_id_does_not_grant_access_and_revocation_prevents_rebinding(self):
        self.provision()
        body = {'device_id': 'door_a'}
        path = '/api/mfa/bind/device'
        self.assertEqual(self.client.post(path, json=body, headers=self.headers['alice']).status_code, 403)
        self.grant()
        self.assertEqual(self.client.post(path, json=body, headers=self.headers['alice']).status_code, 200)
        self.assertEqual(self.client.get('/api/device/status?device_id=door_a', headers=self.headers['bob']).status_code, 403)
        self.assertEqual(self.client.get('/api/device/status', headers=self.headers['bob']).json, [])
        self.grant(revoke=True)
        self.assertEqual(self.client.post(path, json=body, headers=self.headers['alice']).status_code, 403)

    def test_private_images_validate_bytes_and_enforce_device_scope(self):
        session = self.handshake(self.provision())
        self.grant()
        output = BytesIO()
        Image.new('RGB', (16, 16), 'red').save(output, format='PNG')
        def upload(raw):
            packet = SecureEnvelope.seal(session, {'device_id': 'door_a', 'image': base64.b64encode(raw).decode()})
            return self.client.post('/api/secure/upload', json=packet)
        self.assertEqual(upload(b'<script>not an image</script>').status_code, 400)
        response = upload(output.getvalue())
        self.assertEqual(response.status_code, 200, response.json)
        path = response.json['snapshot']
        self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(self.client.get(path, headers=self.headers['bob']).status_code, 403)
        response = self.client.get(path, headers=self.headers['alice'])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'image/jpeg')
        response.close()
        self.assertEqual(self.client.get('/static/captures/' + path.split('/')[-1]).status_code, 404)
        self.assertEqual(self.client.post('/api/snapshot/clear', json={'snapshot': path}, headers=self.headers['bob']).status_code, 403)
        self.assertEqual(self.client.post('/api/snapshot/clear', json={'snapshot': path}, headers=self.headers['alice']).status_code, 200)
        self.assertEqual(self.client.get(path, headers=self.headers['alice']).status_code, 404)

    def test_alarms_and_unencrypted_upload_are_not_public(self):
        self.assertEqual(self.client.get('/api/alarms').status_code, 401)
        self.assertEqual(self.client.get('/api/alarms', headers=self.headers['bob']).status_code, 403)
        self.assertEqual(self.client.post('/api/trigger_alarm', json={}).status_code, 401)
        self.assertEqual(self.client.post('/api/upload_frame').status_code, 401)
        self.assertEqual(self.client.get('/video_feed').status_code, 410)

    def test_password_limit_survives_new_app_and_exposes_retry_after(self):
        for _ in range(10):
            self.assertEqual(self.client.post('/api/login/pre', json={'username': 'absent', 'password': 'x'}).status_code, 401)
        other = create_app(self.config)
        result = other.test_client().post('/api/login/pre', json={'username': 'absent', 'password': 'x'})
        self.assertEqual(result.status_code, 429)
        self.assertGreater(int(result.headers['Retry-After']), 0)
        with other.app_context():
            db.session.remove()
            db.engine.dispose()

    def test_concurrent_admission_respects_exact_budget(self):
        def hit(_):
            with self.app.app_context():
                return admit('concurrency', 'identity', 3)[0]
        with ThreadPoolExecutor(max_workers=6) as pool:
            self.assertEqual(sum(pool.map(hit, range(12))), 3)

    def test_command_guard_persists_replay_and_binds_path_and_body(self):
        root = Path(__file__).resolve().parents[3]
        spec = importlib.util.spec_from_file_location('command_guard_test', root / 'paspberry_pi/command_guard.py')
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)
        body, stamp, nonce = b'{"request_id":"one"}', str(int(time.time())), 'a' * 32
        key = hashlib.sha256(b'smart-lock-backend-command\0' + b'd' * 48).digest()
        signature = hmac.new(key, json.dumps(['POST', '/auth_challenge', stamp, nonce, hashlib.sha256(body).hexdigest()], separators=(',', ':')).encode(), hashlib.sha256).hexdigest()
        headers = {'Content-Type': 'application/json', 'X-Command-Time': stamp, 'X-Command-Nonce': nonce, 'X-Command-Signature': signature}
        with patch.dict('os.environ', {'DEVICE_STATE_DIR': self.tmp.name}):
            for index in range(2):
                app = Flask('guard')
                guard.register_command_guard(app, types.SimpleNamespace(device_password='d' * 48))
                app.add_url_rule('/auth_challenge', view_func=lambda: {'ok': True}, methods=['POST'])
                client = app.test_client()
                self.assertEqual(client.post('/auth_challenge', data=body + b' ', headers=headers).status_code, 401)
                self.assertEqual(client.post('/auth_challenge', data=body, headers=headers).status_code, 200 if index == 0 else 409)

    def test_commands_expire_and_sync_response_cannot_be_replayed_or_modified(self):
        session = self.handshake(self.provision())
        self.grant()
        with self.app.app_context():
            command = enqueue('door_a', 'UNLOCKED', User.query.filter_by(username='alice').one().id)
            db.session.commit()
            command_id = command.id
        packet = SecureEnvelope.seal(session, {'device_id': 'door_a'})
        result = self.client.post('/api/lock/sync', json=packet)
        self.assertEqual(result.status_code, 200, result.json)
        body = SecureResponse.verify(session, packet['header'], '/api/lock/sync', result.json)
        self.assertEqual(body['command']['id'], command_id)
        other = SecureEnvelope.seal(session, {'device_id': 'door_a'})
        with self.assertRaises(ValueError):
            SecureResponse.verify(session, other['header'], '/api/lock/sync', result.json)
        tampered = result.json
        tampered['body']['command']['target_status'] = 'LOCKED'
        with self.assertRaises(ValueError):
            SecureResponse.verify(session, packet['header'], '/api/lock/sync', tampered)
        with self.app.app_context():
            db.session.get(DoorCommand, command_id).expires_at = time.time() - 1
            db.session.commit()
        result = self.client.post('/api/lock/sync', json=other)
        self.assertIsNone(SecureResponse.verify(session, other['header'], '/api/lock/sync', result.json)['command'])
        status = self.client.get('/api/lock/commands/' + command_id, headers=self.headers['alice']).json
        self.assertEqual(status['status'], 'expired')
        self.assertFalse(status['hardware_confirmed'])

    def test_hardware_ack_requires_device_identity_state_and_live_command(self):
        session = self.handshake(self.provision())
        self.grant()
        with self.app.app_context():
            command = enqueue('door_a', 'LOCKED', User.query.filter_by(username='alice').one().id)
            db.session.commit()
            command_id = command.id
        def ack(state):
            packet = SecureEnvelope.seal(session, dict(device_id='door_a', command_id=command_id, status='executed', reported_status=state))
            return self.client.post('/api/lock/ack', json=packet)
        self.assertEqual(ack('UNLOCKED').status_code, 400)
        self.assertEqual(ack('LOCKED').status_code, 200)
        self.assertEqual(ack('LOCKED').status_code, 200)
        status = self.client.get('/api/lock/commands/' + command_id, headers=self.headers['alice']).json
        self.assertTrue(status['hardware_confirmed'])

    def test_revoked_user_and_superseded_commands_are_not_delivered(self):
        session = self.handshake(self.provision())
        self.grant()
        with self.app.app_context():
            uid = User.query.filter_by(username='alice').one().id
            first = enqueue('door_a', 'UNLOCKED', uid)
            db.session.commit()
            second = enqueue('door_a', 'LOCKED', uid)
            db.session.commit()
            self.assertEqual(db.session.get(DoorCommand, first.id).status, 'superseded')
            second_id = second.id
        self.grant(revoke=True)
        packet = SecureEnvelope.seal(session, {'device_id': 'door_a'})
        response = self.client.post('/api/lock/sync', json=packet)
        self.assertIsNone(SecureResponse.verify(session, packet['header'], '/api/lock/sync', response.json)['command'])
        with self.app.app_context():
            self.assertEqual(db.session.get(DoorCommand, second_id).status, 'revoked')

    def create_command(self, target='UNLOCKED'):
        with self.app.app_context():
            command = enqueue('door_a', target, User.query.filter_by(username='alice').one().id)
            db.session.commit()
            return command.id

    def send_ack(self, session, command_id, status='executed', reported_status='UNLOCKED'):
        packet = SecureEnvelope.seal(session, dict(
            device_id='door_a', command_id=command_id, status=status,
            reported_status=reported_status))
        return self.client.post('/api/lock/ack', json=packet)

    def test_regrant_cannot_resurrect_revoked_command(self):
        session = self.handshake(self.provision())
        self.grant()
        command_id = self.create_command()
        self.grant(revoke=True)
        self.grant()
        self.assertEqual(self.send_ack(session, command_id).status_code, 409)
        response = self.client.get('/api/lock/commands/' + command_id, headers=self.headers['alice'])
        self.assertEqual(response.json['status'], 'revoked')
        self.assertFalse(response.json['hardware_confirmed'])

    def test_secret_rotation_revokes_pending_commands(self):
        self.provision()
        self.grant()
        command_id = self.create_command()
        session = self.handshake(self.provision('e' * 48))
        self.assertEqual(self.send_ack(session, command_id).status_code, 409)
        with self.app.app_context():
            self.assertEqual(db.session.get(DoorCommand, command_id).status, 'revoked')

    def test_ack_rechecks_lockout_and_account_status_without_sync(self):
        session = self.handshake(self.provision())
        self.grant()
        for reason in ('lockout', 'account'):
            with self.subTest(reason=reason):
                command_id = self.create_command()
                with self.app.app_context():
                    user = User.query.filter_by(username='alice').one()
                    binding = MFACredential.query.filter_by(user_id=user.id, credential_type='device').one()
                    binding.is_locked = reason == 'lockout'
                    user.status = 'rejected' if reason == 'account' else 'approved'
                    db.session.commit()
                self.assertEqual(self.send_ack(session, command_id).status_code, 409)
                with self.app.app_context():
                    command = db.session.get(DoorCommand, command_id)
                    self.assertEqual(command.status, 'revoked')
                    self.assertIsNone(command.acknowledged_at)

    def test_ack_persists_expiry_and_rejects_malformed_identifiers(self):
        session = self.handshake(self.provision())
        self.grant()
        command_id = self.create_command()
        for invalid in (None, [], {}, 123, '', 'x' * 65):
            with self.subTest(command_id=invalid):
                self.assertEqual(self.send_ack(session, invalid).status_code, 400)
        with self.app.app_context():
            db.session.get(DoorCommand, command_id).expires_at = time.time() - 1
            db.session.commit()
        self.assertEqual(self.send_ack(session, command_id).status_code, 409)
        with self.app.app_context():
            self.assertEqual(db.session.get(DoorCommand, command_id).status, 'expired')

    def test_terminal_ack_is_idempotent_after_expiry_and_cannot_be_rewritten(self):
        session = self.handshake(self.provision())
        self.grant()
        command_id = self.create_command()
        self.assertEqual(self.send_ack(session, command_id).status_code, 200)
        with self.app.app_context():
            command = db.session.get(DoorCommand, command_id)
            acknowledged_at = command.acknowledged_at
            command.expires_at = time.time() - 1
            db.session.commit()
        self.grant(revoke=True)
        self.assertEqual(self.send_ack(session, command_id).status_code, 200)
        self.assertEqual(self.send_ack(session, command_id, status='failed').status_code, 409)
        with self.app.app_context():
            command = db.session.get(DoorCommand, command_id)
            self.assertEqual(command.status, 'executed')
            self.assertEqual(command.acknowledged_at, acknowledged_at)

    def test_status_read_persists_lockout_invalidation(self):
        self.provision()
        self.grant()
        command_id = self.create_command()
        with self.app.app_context():
            MFACredential.query.filter_by(credential_type='device').update({'is_locked': True})
            db.session.commit()
        response = self.client.get('/api/lock/commands/' + command_id, headers=self.headers['alice'])
        self.assertEqual(response.json['status'], 'revoked')
        self.assertFalse(response.json['hardware_confirmed'])
        with self.app.app_context():
            self.assertEqual(db.session.get(DoorCommand, command_id).status, 'revoked')

    def test_concurrent_conflicting_receipts_preserve_one_terminal_outcome(self):
        from app.door_commands import acknowledge
        self.provision()
        self.grant()
        command_id = self.create_command()
        def record(status):
            with self.app.app_context():
                result = acknowledge(db.session.get(DoorCommand, command_id), status, 'UNLOCKED')
                db.session.commit()
                return result.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            codes = list(pool.map(record, ('executed', 'failed')))
        self.assertEqual(sorted(codes), [200, 409])
        with self.app.app_context():
            command = db.session.get(DoorCommand, command_id)
            self.assertEqual(command.status, 'executed' if codes[0] == 200 else 'failed')
            self.assertIsNotNone(command.acknowledged_at)

    def test_readiness_checks_all_tables_not_only_users(self):
        from sqlalchemy import text
        self.assertEqual(self.client.get('/health/ready').status_code, 200)
        with self.app.app_context():
            db.session.execute(text('DROP TABLE alarm_deliveries'))
            db.session.commit()
        self.assertEqual(self.client.get('/health/ready').status_code, 503)
        self.assertEqual(self.client.get('/health/live').status_code, 200)

    def test_alarm_outbox_retries_without_sending_from_request(self):
        from app.models import AlarmDelivery, AlarmLog
        from app.notifications import deliver_pending, queue_alarm
        with self.app.app_context():
            alarm = AlarmLog(alarm_type='test', message='local fixture')
            db.session.add(alarm)
            queue_alarm(alarm)
            db.session.commit()
            self.assertEqual(db.session.get(AlarmDelivery, alarm.id).status, 'disabled')
            self.app.config.update(SENDER_EMAIL='test@example.invalid', SENDER_PASSWORD='fixture', RECEIVER_EMAIL='test@example.invalid')
            alarm = AlarmLog(alarm_type='test', message='local fixture')
            db.session.add(alarm)
            queue_alarm(alarm)
            db.session.commit()
            alarm_id = alarm.id
            def fail(_):
                raise OSError('offline fixture')
            with self.assertLogs('app.notifications', level='ERROR'):
                self.assertEqual(deliver_pending(sender=fail), 1)
            delivery = db.session.get(AlarmDelivery, alarm_id)
            self.assertEqual(delivery.status, 'pending')
            self.assertEqual(delivery.attempts, 1)
            self.assertEqual(deliver_pending(sender=lambda _: self.fail('Retry must wait')), 0)
            delivery.next_attempt_at = 0
            db.session.commit()
            sent = []
            self.assertEqual(deliver_pending(sender=lambda item: sent.append(item.id)), 1)
            self.assertEqual(sent, [alarm_id])
            self.assertEqual(db.session.get(AlarmDelivery, alarm_id).status, 'sent')
            self.assertEqual(deliver_pending(sender=lambda _: self.fail('Duplicate email')), 0)

    def test_crashed_final_email_attempt_is_not_sent_again(self):
        from app.models import AlarmDelivery, AlarmLog
        from app.notifications import deliver_pending, MAX_ATTEMPTS
        with self.app.app_context():
            alarm = AlarmLog(alarm_type='fixture', message='local only')
            db.session.add(alarm)
            db.session.flush()
            delivery = AlarmDelivery(alarm_id=alarm.id, status='sending',
                                     attempts=MAX_ATTEMPTS, next_attempt_at=0, lease_id='crashed')
            db.session.add(delivery)
            db.session.commit()
            self.assertEqual(deliver_pending(sender=lambda _: self.fail('Budget exhausted')), 0)
            db.session.refresh(delivery)
            self.assertEqual(delivery.status, 'failed')
            self.assertIsNone(delivery.lease_id)

    def test_email_attempt_is_reserved_before_network_io(self):
        from app.models import AlarmDelivery, AlarmLog
        from app.notifications import deliver_pending
        with self.app.app_context():
            alarm = AlarmLog(alarm_type='fixture', message='local only')
            db.session.add(alarm)
            db.session.flush()
            db.session.add(AlarmDelivery(alarm_id=alarm.id))
            db.session.commit()
            def inspect_reservation(payload):
                with self.app.app_context():
                    delivery = db.session.get(AlarmDelivery, payload.id)
                    self.assertEqual(delivery.attempts, 1)
                    self.assertEqual(delivery.status, 'sending')
                    self.assertGreater(delivery.next_attempt_at, time.time())
            self.assertEqual(deliver_pending(sender=inspect_reservation), 1)
            self.assertEqual(db.session.get(AlarmDelivery, alarm.id).status, 'sent')

    def test_online_status_is_derived_without_writing_device_records(self):
        from datetime import datetime, timedelta
        from app.models import Device
        from sqlalchemy import event
        self.provision()
        self.grant()
        with self.app.app_context():
            device = Device.query.filter_by(device_id='door_a').one()
            self.assertIsNone(device.battery)
            device.last_update = datetime.now() - timedelta(minutes=3)
            device.is_online = True
            db.session.commit()
            statements = []
            def observe(conn, cursor, statement, parameters, context, executemany):
                statements.append(statement)
            event.listen(db.engine, 'before_cursor_execute', observe)
            try:
                result = self.client.get('/api/device/status', headers=self.headers['alice'])
                self.assertFalse(result.json[0]['is_online'])
            finally:
                event.remove(db.engine, 'before_cursor_execute', observe)
            self.assertFalse(any(sql.lstrip().upper().startswith(('UPDATE', 'INSERT', 'DELETE')) for sql in statements))

    def test_media_retention_is_previewed_bounded_and_preserves_recent_assets(self):
        from datetime import datetime, timedelta
        from app.maintenance import prune_media
        with self.app.app_context():
            directory = Path(self.app.config['UPLOAD_FOLDER'])
            directory.mkdir()
            for digit, age in (('a', 40), ('b', 1)):
                filename = digit * 32 + '.jpg'
                (directory / filename).write_bytes(b'fixture')
                db.session.add(MediaAsset(filename=filename, device_id='door_a', created_at=datetime.now() - timedelta(days=age)))
            db.session.commit()
            self.assertEqual(prune_media(30), 1)
            self.assertEqual(len(list(directory.iterdir())), 2)
            self.assertEqual(prune_media(30, apply=True), 1)
            self.assertEqual([p.name for p in directory.iterdir()], ['b' * 32 + '.jpg'])
            self.assertEqual(MediaAsset.query.count(), 1)

    def test_concurrent_alarm_workers_claim_one_delivery(self):
        from app.models import AlarmDelivery, AlarmLog
        from app.notifications import deliver_pending
        from threading import Barrier, Lock
        with self.app.app_context():
            alarm = AlarmLog(alarm_type='fixture', message='no external email')
            db.session.add(alarm)
            db.session.flush()
            db.session.add(AlarmDelivery(alarm_id=alarm.id))
            db.session.commit()
        barrier, mutex, sent = Barrier(2), Lock(), []
        def sender(alarm):
            with mutex:
                sent.append(alarm.id)
        def worker(_):
            with self.app.app_context():
                barrier.wait(timeout=5)
                return deliver_pending(sender=sender)
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(worker, range(2))), 1)
        self.assertEqual(len(sent), 1)

    def test_media_cleanup_validates_entire_batch_before_deleting(self):
        from datetime import datetime, timedelta
        from app.maintenance import prune_media
        with self.app.app_context():
            directory = Path(self.app.config['UPLOAD_FOLDER'])
            directory.mkdir()
            filename = 'a' * 32 + '.jpg'
            (directory / filename).write_bytes(b'preserve on invalid batch')
            db.session.add(MediaAsset(filename=filename, device_id='door_a',
                                      created_at=datetime.now() - timedelta(days=60)))
            db.session.add(MediaAsset(filename='../invalid.jpg', device_id='door_a',
                                      created_at=datetime.now() - timedelta(days=40)))
            db.session.commit()
            with self.assertRaises(ValueError):
                prune_media(30, apply=True)
            self.assertTrue((directory / filename).is_file())
            self.assertEqual(MediaAsset.query.count(), 2)

    def test_device_heartbeat_never_claims_physical_execution(self):
        from unittest.mock import Mock
        root = Path(__file__).resolve().parents[3]
        spec = importlib.util.spec_from_file_location('device_runtime_test', root / 'paspberry_pi/runtime.py')
        runtime = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runtime)
        transmitter, camera = Mock(), Mock()
        worker = runtime.HeartbeatWorker(transmitter, camera)
        for frame, expected in ((object(), 'ONLINE'), (None, 'OFFLINE')):
            camera.capture_frame.return_value = frame
            worker.report_once()
            transmitter.heartbeat.assert_called_with('UNKNOWN', camera_status=expected)
        camera.capture_frame.side_effect = OSError('fixture camera failure')
        with self.assertLogs('device_runtime_test', level='ERROR'):
            worker.report_once()
        transmitter.heartbeat.assert_called_with('UNKNOWN', camera_status='ERROR')
        transmitter.acknowledge_command.assert_not_called()

    def test_backup_restore_checks_content_and_never_overwrites_live_data(self):
        root = Path(__file__).resolve().parents[3]
        spec = importlib.util.spec_from_file_location('backup_test', root / 'deploy/backup.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        source = Path(self.tmp.name) / 'backup-source'
        source.mkdir()
        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect(source / 'smart_lock.db')) as connection:
            connection.execute('CREATE TABLE example (value TEXT)')
            connection.execute("INSERT INTO example VALUES ('restored')")
            connection.commit()
        (source / 'captures').mkdir()
        (source / 'captures/one.jpg').write_bytes(b'backup-fixture')
        archive = Path(self.tmp.name) / 'backup.zip'
        target = Path(self.tmp.name) / 'restore'
        module.backup(source, archive)
        module.restore(archive, target)
        self.assertEqual((target / 'captures/one.jpg').read_bytes(), b'backup-fixture')
        with self.assertRaises(ValueError):
            module.restore(archive, target)
        malicious = Path(self.tmp.name) / 'malicious.zip'
        with zipfile.ZipFile(malicious, 'w') as output:
            output.writestr('manifest.json', json.dumps({'smart_lock.db': 'x', '../escape': 'y'}))
            output.writestr('smart_lock.db', b'damaged')
        empty = Path(self.tmp.name) / 'rejected'
        with self.assertRaises(ValueError):
            module.restore(malicious, empty)
        self.assertEqual(list(empty.iterdir()), [])
        # Valid hashes do not make an invalid SQLite database a valid backup.
        damaged = Path(self.tmp.name) / 'damaged.zip'
        raw = b'not a SQLite database'
        with zipfile.ZipFile(damaged, 'w') as output:
            output.writestr('manifest.json', json.dumps({'smart_lock.db': hashlib.sha256(raw).hexdigest()}))
            output.writestr('smart_lock.db', raw)
        with self.assertRaises(sqlite3.DatabaseError):
            module.restore(damaged, empty)
        self.assertEqual(list(empty.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
