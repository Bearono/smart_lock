"""Software readiness cannot confuse a running process with configured face assets."""
import os
from pathlib import Path
import secrets
import sys
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cv/code'))


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'SMART_LOCK_ENV': 'production',
            'BACKEND_URL': 'https://backend.invalid', 'SMART_LOCK_DEVICE_PASSWORD': secrets.token_hex(32)})
        self.env.start()
        from app import app
        self.client = app.test_client()

    def tearDown(self):
        self.env.stop()

    def test_missing_or_tampered_models_are_not_ready(self):
        with patch('model_manifest.verify_models', side_effect=ValueError('unverified model')):
            result = self.client.get('/health/ready')
            self.assertEqual(result.status_code, 503)
            self.assertEqual(result.json['reason'], 'face_assets_invalid')

    def test_empty_templates_are_not_ready(self):
        with patch('model_manifest.verify_models'), patch('anti_spoof.verify_pad_model'), patch('template_store.load_templates', return_value={}):
            result = self.client.get('/health/ready')
            self.assertEqual(result.status_code, 503)
            self.assertEqual(result.json['reason'], 'face_templates_missing')

    def test_configured_software_does_not_assume_physical_camera_or_lock(self):
        with patch('model_manifest.verify_models'), patch('anti_spoof.verify_pad_model'), patch('template_store.load_templates', return_value={'fixture': object()}), patch('app.camera.capture_frame', side_effect=AssertionError('readiness must not access camera')):
            result = self.client.get('/health/ready')
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json, {'scope': 'software', 'status': 'ok'})

    def test_missing_pad_model_prevents_production_readiness(self):
        with patch('model_manifest.verify_models'), patch('anti_spoof.verify_pad_model', side_effect=ValueError('missing PAD model')):
            result = self.client.get('/health/ready')
            self.assertEqual(result.status_code, 503)
            self.assertEqual(result.json['reason'], 'face_assets_invalid')

    def signed_challenge(self):
        import hashlib, hmac, json, time
        from app import transmitter
        body = json.dumps({'request_id': 'fixture-request', 'nonce': 'fixture-session-nonce'}).encode()
        stamp, nonce = str(int(time.time())), secrets.token_hex(16)
        message = json.dumps(['POST', '/auth_challenge', stamp, nonce,
            hashlib.sha256(body).hexdigest()], separators=(',', ':')).encode()
        key = hashlib.sha256(b'smart-lock-backend-command\0' + transmitter.device_password.encode()).digest()
        headers = {'X-Command-Time': stamp, 'X-Command-Nonce': nonce,
                   'X-Command-Signature': hmac.new(key, message, hashlib.sha256).hexdigest()}
        with TemporaryDirectory() as directory, patch.dict(os.environ, {'DEVICE_STATE_DIR': directory}):
            return self.client.post('/auth_challenge', data=body, content_type='application/json', headers=headers)

    def test_signed_production_challenge_sends_same_frame_pad_score(self):
        import numpy as np
        frame = np.zeros((32, 32, 3), dtype=np.uint8)
        with patch('app.camera.capture_frame', return_value=frame) as capture, \
                patch('recognize.recognize_with_pad', return_value=('fixture', 0.96, 0.83)) as inference, \
                patch('app.transmitter.send_auth_result', return_value={'http_status': 200}) as send:
            result = self.signed_challenge()
            self.assertEqual(result.status_code, 200, result.json)
            capture.assert_called_once()
            self.assertIs(inference.call_args.args[0], frame)
            send.assert_called_once()
            self.assertIs(send.call_args.kwargs['frame'], frame)
            self.assertEqual(send.call_args.kwargs['liveness_score'], 0.83)
            self.assertEqual(send.call_args.kwargs['session_nonce'], 'fixture-session-nonce')

    def test_pad_failure_cannot_send_identity_only_result(self):
        with patch('app.camera.capture_frame', return_value=object()), \
                patch('recognize.recognize_with_pad', side_effect=ValueError('invalid PAD model')), \
                patch('app.transmitter.send_auth_result') as send:
            self.assertEqual(self.signed_challenge().status_code, 500)
            send.assert_not_called()


if __name__ == '__main__':
    unittest.main()
