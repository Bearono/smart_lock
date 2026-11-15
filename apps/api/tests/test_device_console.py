"""Local camera console: explicit capture, bounded work, and loopback request boundaries."""
import http.client
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'deploy'))
from device_console import ConsoleState, ThreadingHTTPServer, make_handler


class DeviceConsoleTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.controller = Mock()
        self.controller.capture.return_value = ({'snapshot': '/api/media/test.jpg', 'received_at': '2026-11-15T12:00:00Z'}, b'jpeg-fixture')
        self.controller.analyze.return_value = {'face_count': 1, 'identity': 'admin', 'similarity': .96, 'pad_score': .91}
        self.state = ConsoleState(self.controller, self.temp.name)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), lambda *a, **k: None)
        self.origin = 'http://127.0.0.1:' + str(self.server.server_port)
        self.server.RequestHandlerClass = make_handler(self.state, self.origin)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.wait_idle()
        self.temp.cleanup()

    def request(self, method, path, headers=None, body=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        result = response.status, response.read(), dict(response.getheaders())
        connection.close()
        return result

    def wait_idle(self):
        deadline = time.monotonic() + 3
        while self.state.snapshot()['busy'] and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertFalse(self.state.snapshot()['busy'])

    def test_get_does_not_capture_and_host_rebinding_is_rejected(self):
        for route in ('/', '/api/state'):
            status, _, headers = self.request('GET', route)
            self.assertEqual(status, 200)
            self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(self.request('GET', '/api/state', {'Host': 'attacker.invalid'})[0], 403)
        self.controller.capture.assert_not_called()

    def test_only_same_origin_csrf_post_can_start_capture(self):
        payload = json.dumps({'label': 'live_front'})
        headers = {'Content-Type': 'application/json', 'Origin': 'https://attacker.invalid', 'X-Test-CSRF': self.state.token}
        self.assertEqual(self.request('POST', '/api/capture', headers, payload)[0], 403)
        headers['Origin'] = self.origin
        headers['X-Test-CSRF'] = 'incorrect'
        self.assertEqual(self.request('POST', '/api/capture', headers, payload)[0], 403)
        self.controller.capture.assert_not_called()
        headers['X-Test-CSRF'] = self.state.token
        self.assertEqual(self.request('POST', '/api/capture', headers, payload)[0], 202)
        self.wait_idle()
        result = self.state.snapshot()['history'][0]
        self.assertTrue(result['sample_passed'])
        self.assertIn('not_door_authorization', result['scope'])
        self.assertEqual(self.request('GET', '/image/' + result['id'])[1], b'jpeg-fixture')
        self.assertEqual(self.request('GET', '/image/../../secret')[0], 404)
        self.assertTrue((Path(self.temp.name) / (result['id'] + '.json')).is_file())

    def test_duplicate_click_is_rejected_while_photo_is_being_analyzed(self):
        entered, release = threading.Event(), threading.Event()
        def analyze(_):
            entered.set()
            release.wait(2)
            raise RuntimeError('diagnostic fixture failed')
        self.controller.analyze.side_effect = analyze
        self.assertTrue(self.state.start('live_front'))
        try:
            self.assertTrue(entered.wait(1))
            self.assertEqual(self.state.snapshot()['phase'], 'analyzing')
            self.assertEqual(len(self.state.snapshot()['history']), 1)
            self.assertFalse(self.state.start('live_front'))
        finally:
            release.set()
        self.wait_idle()
        item = self.state.snapshot()['history'][0]
        self.assertEqual(item['status'], 'failed')
        self.assertNotIn('sample_passed', item)
        self.assertIn('snapshot', item)
        self.controller.capture.assert_called_once()

    def test_bad_label_never_touches_camera(self):
        with self.assertRaises(ValueError):
            self.state.start('unexpected')
        self.controller.capture.assert_not_called()


if __name__ == '__main__':
    unittest.main()
