"""Software acceptance over real loopback HTTP, using disposable services only.

The device fixture supplies synthetic recognition and receipts explicitly for
protocol testing. No camera, actuator, external host or real SMTP is contacted.
"""
from contextlib import ExitStack, contextmanager
import importlib.util
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Thread
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pyotp
import requests
from flask import Flask, jsonify, request
from werkzeug.serving import make_server, WSGIRequestHandler

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app, db
from app.routes.security_protocol import SecureEnvelope, SecureResponse, Spake2Client


class QuietHandler(WSGIRequestHandler):
    def log_request(self, code='-', size='-'):
        pass


@contextmanager
def serve(app):
    server = make_server('127.0.0.1', 0, app, threaded=True, request_handler=QuietHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def http(method, url, **kwargs):
    with requests.Session() as session:
        session.trust_env = False
        return session.request(method, url, timeout=10, **kwargs)


class HTTPDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        directory = Path(self.stack.enter_context(TemporaryDirectory(prefix='smart-lock-http-')))
        self.directory = directory
        self.app = create_app({
            'DEPLOYMENT_ENV': 'production', 'TESTING': False, 'AUTO_INIT_DB': False,
            'SECRET_KEY': 'http-fixture-app-secret-' + 's' * 32,
            'JWT_SECRET_KEY': 'http-fixture-jwt-secret-' + 'j' * 32,
            'ALLOW_DEMO_DEVICES': False, 'ALLOW_LEGACY_SECURE_UPLOAD': False,
            'DEVICE_DISPATCH_REQUIRED': True, 'BCRYPT_LOG_ROUNDS': 4,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + (directory / 'app.db').as_posix(),
            'UPLOAD_FOLDER': str(directory / 'captures'),
            'SENDER_EMAIL': '', 'SENDER_PASSWORD': '', 'RECEIVER_EMAIL': '',
        })
        self.stack.callback(self.dispose)
        self.cli = self.app.test_cli_runner()
        self.run_cli('init-db')
        self.run_cli('create-admin', '--username', 'operator', '--password', 'fixture-admin-password')
        self.backend = self.stack.enter_context(serve(self.app))
        self.device_password = 'http-fixture-device-secret-' + 'd' * 32
        device = Flask('software-device-fixture')
        root = Path(__file__).resolve().parents[3]
        spec = importlib.util.spec_from_file_location('http_guard', root / 'paspberry_pi/command_guard.py')
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)
        self.stack.enter_context(patch.dict('os.environ', {'DEVICE_STATE_DIR': str(directory / 'device')}))
        guard.register_command_guard(device, SimpleNamespace(device_password=self.device_password))

        @device.post('/auth_challenge')
        def challenge():
            body = request.get_json()
            packet = SecureEnvelope.seal(self.device_session, {
                'device_id': 'http_door', 'request_id': body['request_id'],
                'session_nonce': body['nonce'], 'face_user_id': 'alice', 'similarity_score': 0.99,
            })
            response = self.api('POST', '/api/mfa/open-door/face-result', json=packet)
            return jsonify(status='success' if response.ok else 'error', backend_reply=response.json()), response.status_code

        device_url = self.stack.enter_context(serve(device))
        self.device_url = device_url
        self.run_cli('provision-device', '--device-id', 'http_door', '--service-url', device_url,
                     '--password', self.device_password)
        self.secrets = {}
        self.admin_headers = self.login('operator', 'fixture-admin-password')
        self.assertEqual(self.api('POST', '/api/register', json={
            'username': 'alice', 'password': 'fixture-user-password'}).status_code, 201)
        users = self.api('GET', '/api/admin/users', headers=self.admin_headers).json()
        self.user_id = next(user['id'] for user in users if user['username'] == 'alice')
        self.assertEqual(self.api('POST', f'/api/admin/users/{self.user_id}/approve', headers=self.admin_headers).status_code, 200)
        self.assertEqual(self.api('PUT', f'/api/admin/users/{self.user_id}/devices/http_door',
                                  headers=self.admin_headers, json={'granted': True}).status_code, 200)
        self.user_headers = self.login('alice', 'fixture-user-password')
        self.assertEqual(self.api('POST', '/api/mfa/bind/device', headers=self.user_headers,
                                  json={'device_id': 'http_door'}).status_code, 200)
        client = Spake2Client('http_door', self.device_password)
        state, message = client.begin()
        reply = self.api('POST', '/api/security/spake2/start', json=message)
        self.assertEqual(reply.status_code, 200, reply.text)
        self.device_session = client.finish(state, reply.json())

    def dispose(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()

    def run_cli(self, *args):
        result = self.cli.invoke(args=list(args))
        self.assertEqual(result.exit_code, 0, result.output)

    def api(self, method, path, **kwargs):
        return http(method, self.backend + path, **kwargs)

    def login(self, username, password):
        response = self.api('POST', '/api/login/pre', json={'username': username, 'password': password})
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        if not data['totp_bound']:
            self.secrets[username] = data['secret']
            self.assertTrue(data['qr_image'].startswith('data:image/png;base64,'))
        path = '/api/login/mfa/verify' if data['totp_bound'] else '/api/login/mfa/bind'
        response = self.api('POST', path, json={
            'pre_token': data['pre_token'], 'code': pyotp.TOTP(self.secrets[username]).now()})
        self.assertEqual(response.status_code, 200, response.text)
        return {'Authorization': 'Bearer ' + response.json()['access_token']}

    def test_registered_user_to_signed_challenge_and_execution_receipt(self):
        self.assertEqual(self.api('GET', '/health/ready').status_code, 200)
        self.assertEqual(http('POST', self.device_url + '/auth_challenge', json={}).status_code, 401)
        response = self.api('POST', '/api/mfa/open-door/request', headers=self.user_headers,
                            json={'device_id': 'http_door'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()['requires_totp'])
        response = self.api('POST', '/api/mfa/open-door/confirm', headers=self.user_headers, json={
            'request_id': response.json()['request_id'], 'totp_code': pyotp.TOTP(self.secrets['alice']).now()})
        self.assertEqual(response.status_code, 200, response.text)
        credential = response.json()
        response = self.api('POST', '/api/lock/unlock-token/verify', json=credential)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()['hardware_confirmed'])
        spec = importlib.util.spec_from_file_location(
            'http_executor', Path(__file__).resolve().parents[3] / 'paspberry_pi/command_executor.py')
        executor_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(executor_module)
        fixture = self

        class HTTPTransport:
            def sync_lock(self):
                packet = SecureEnvelope.seal(fixture.device_session, {'device_id': 'http_door'})
                reply = fixture.api('POST', '/api/lock/sync', json=packet)
                reply.raise_for_status()
                return SecureResponse.verify(fixture.device_session, packet['header'], '/api/lock/sync', reply.json())

            def acknowledge_command(self, command_id, status, reported_status):
                packet = SecureEnvelope.seal(fixture.device_session, dict(
                    device_id='http_door', command_id=command_id, status=status, reported_status=reported_status))
                reply = fixture.api('POST', '/api/lock/ack', json=packet)
                reply.raise_for_status()
                return reply.json()

        class SoftwareActuator:
            state = 'LOCKED'
            calls = 0

            def set_state(self, target):
                self.state = target
                self.calls += 1

            def read_state(self):
                return self.state

        actuator = SoftwareActuator()
        executor = executor_module.CommandExecutor(HTTPTransport(), actuator, self.directory / 'executions.db')
        executor.run_once()
        executor.run_once()
        self.assertEqual(actuator.calls, 1)
        outcome = self.api('POST', '/api/lock/command-status', json=credential).json()
        self.assertEqual(outcome['status'], 'executed')
        self.assertTrue(outcome['hardware_confirmed'])
        self.assertEqual(self.api('POST', '/api/lock/unlock-token/verify', json=credential).status_code, 401)

    def test_web_grant_revocation_reaches_guest_command(self):
        response = self.api('POST', '/api/mfa/guest/create', headers=self.user_headers,
                            json={'device_id': 'http_door', 'guest_name': 'fixture visitor'})
        self.assertEqual(response.status_code, 200, response.text)
        credential = self.api('POST', '/api/mfa/guest/verify', json={'pass_code': response.json()['pass_code']}).json()
        self.assertEqual(self.api('POST', '/api/lock/unlock-token/verify', json=credential).status_code, 200)
        path = f'/api/admin/users/{self.user_id}/devices/http_door'
        self.assertEqual(self.api('PUT', path, headers=self.user_headers, json={'granted': False}).status_code, 403)
        self.assertEqual(self.api('PUT', path, headers=self.admin_headers, json={'granted': False}).status_code, 200)
        self.assertEqual(self.api('POST', '/api/lock/command-status', json=credential).json()['status'], 'revoked')
        self.assertEqual(self.api('GET', '/api/device/status', headers=self.user_headers).json(), [])
