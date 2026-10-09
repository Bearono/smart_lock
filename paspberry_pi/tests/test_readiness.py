"""Software readiness cannot confuse a running process with configured face assets."""
import os
from pathlib import Path
import secrets
import sys
import unittest
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
        with patch('model_manifest.verify_models'), patch('template_store.load_templates', return_value={}):
            result = self.client.get('/health/ready')
            self.assertEqual(result.status_code, 503)
            self.assertEqual(result.json['reason'], 'face_templates_missing')

    def test_configured_software_does_not_assume_physical_camera_or_lock(self):
        with patch('model_manifest.verify_models'), patch('template_store.load_templates', return_value={'fixture': object()}), patch('app.camera.capture_frame', side_effect=AssertionError('readiness must not access camera')):
            result = self.client.get('/health/ready')
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json, {'scope': 'software', 'status': 'ok'})


if __name__ == '__main__':
    unittest.main()
