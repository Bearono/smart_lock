"""Display-free audio console checks; no recording, playback, or GUI creation."""
import hashlib
import importlib.util
import json
from pathlib import Path
import queue
import tempfile
import threading
import unittest

from smartlock_protocol.audio_d2d import Peer, canonical
from smartlock_protocol.audio import decode, read_wav

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('audio_console_under_test', ROOT / 'deploy/audio_console.py')
console = importlib.util.module_from_spec(spec)
spec.loader.exec_module(console)


class FakeWidget:
    def __init__(self):
        self.options = {}

    def configure(self, **values):
        self.options.update(values)


class FakeRoot:
    def __init__(self):
        self.destroyed = False
        self.scheduled = []

    def after(self, delay, callback):
        self.scheduled.append((delay, callback))

    def destroy(self):
        self.destroyed = True


class AudioConsoleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.controller = console.ConsoleController(self.folder / 'instance/audio-console')
        self.receiver = Peer(self.folder / 'receiver', create=True)
        public = self.receiver.initialize('receiver', 'phone_01')
        self.receiver_public = self.folder / 'receiver.der'
        self.receiver_public.write_bytes(public)

    def pin(self):
        preview = self.controller.preview_receiver(self.receiver_public)
        return self.controller.pin_receiver(self.receiver_public, preview['sha256'])

    def request_file(self, extension='.json'):
        request = self.receiver.create_request('laptop')
        path = self.folder / ('request' + extension)
        path.write_bytes(console.audio_peer.packet_bytes(path, request))
        return path

    def test_initialize_reuses_identity_and_never_overwrites_existing_state(self):
        self.assertIsNone(self.controller.existing_identity())
        first = self.controller.initialize('laptop')
        master = (self.controller.directory / 'master.key').read_bytes()
        other = console.ConsoleController(self.controller.directory)
        self.assertEqual(other.existing_identity(), 'laptop')
        self.assertEqual(other.initialize('laptop'), first)
        with self.assertRaises(ValueError):
            other.initialize('different_name')
        self.assertEqual((self.controller.directory / 'master.key').read_bytes(), master)

    def test_exports_only_public_material_with_unique_local_names(self):
        self.controller.initialize('laptop')
        first, second = self.controller.export_issuer(), self.controller.export_issuer()
        self.assertNotEqual(first['path'], second['path'])
        self.assertEqual(first['path'].parent, self.controller.files)
        self.assertEqual(first['path'].read_bytes(), self.controller.peer.public_key())
        self.assertEqual(first['sha256'], hashlib.sha256(first['path'].read_bytes()).hexdigest())

    def test_pinning_requires_still_matching_previewed_public_key(self):
        preview = self.controller.preview_receiver(self.receiver_public)
        self.assertIsNone(self.controller.receiver_public)
        with self.assertRaises(ValueError):
            self.controller.pin_receiver(self.receiver_public, '0' * 64)
        self.assertIsNone(self.controller.receiver_public)
        pinned = self.controller.pin_receiver(self.receiver_public, preview['sha256'])
        self.assertEqual(pinned['path'].parent, self.controller.files)
        self.assertEqual(self.controller.receiver_public, self.receiver_public.read_bytes())

    def test_full_file_exchange_confirm_before_message_and_replay_gate(self):
        self.controller.initialize('laptop')
        self.controller.import_request(self.request_file('.wav'))
        with self.assertRaises(ValueError):
            self.controller.issue()
        self.pin()
        issued = self.controller.issue()
        self.assertEqual(issued['path'].parent, self.controller.files)
        packet = json.loads(decode(read_wav(issued['path'].read_bytes())))
        confirmation = self.receiver.accept(packet, self.controller.peer.public_key())
        message = self.receiver.seal(packet['binding']['session'], '手机发来的认证消息'.encode())
        message_path = self.folder / 'message.wav'
        message_path.write_bytes(console.audio_peer.packet_bytes(message_path, message))
        with self.assertRaises(ValueError):
            self.controller.decrypt(message_path)
        confirmation_path = self.folder / 'confirm.wav'
        confirmation_path.write_bytes(console.audio_peer.packet_bytes(confirmation_path, confirmation))
        self.assertEqual(self.controller.confirm(confirmation_path)['recipient'], 'phone_01')
        opened = self.controller.decrypt(message_path)
        self.assertEqual(opened['text'], '手机发来的认证消息')
        self.assertFalse(opened['acoustic_checked'])
        self.assertEqual(opened['path'].parent, self.controller.files)
        with self.assertRaises(ValueError):
            self.controller.decrypt(message_path)
        with self.assertRaises(ValueError):
            self.controller.confirm(confirmation_path)

    def test_wrong_issuer_and_untrusted_request_public_key_rejected(self):
        self.controller.initialize('laptop')
        self.pin()
        path = self.request_file()
        request = json.loads(path.read_bytes())
        request['sender'] = 'different_issuer'
        path.write_bytes(canonical(request))
        with self.assertRaises(ValueError):
            self.controller.import_request(path)
        stranger = Peer(self.folder / 'stranger', create=True)
        stranger.initialize('receiver', 'stranger')
        path.write_bytes(canonical(stranger.create_request('laptop')))
        self.controller.import_request(path)
        with self.assertRaises(ValueError):
            self.controller.issue()

    def test_acoustic_gate_is_optional_and_json_cannot_bypass_when_enabled(self):
        self.controller.initialize('laptop')
        model = self.folder / 'model.json'
        model.write_text(json.dumps({'version': 'SL-acoustic-path-v1', 'sample_rate': 48000,
                                    'center_db': [0] * 64, 'scale_db': [0.75] * 64,
                                    'threshold': 1, 'calibration': {'scope': 'synthetic test only'},
                                    'device_id': 'synthetic-path'}))
        result = self.controller.load_model(model)
        self.assertEqual(result['path'].parent, self.controller.files)
        with self.assertRaises(ValueError):
            self.controller.import_request(self.request_file())
        self.controller.clear_model()
        self.assertIsNone(self.controller.fingerprint_model)
        model.write_text('{"threshold": 1}')
        with self.assertRaises(ValueError):
            self.controller.load_model(model)

    def fake_app(self):
        app = object.__new__(console.AudioConsole)
        app.root, app.status = FakeRoot(), FakeWidget()
        app.worker, app.closing, app.request_expires = None, False, 0
        app.controls, app.events = [], queue.Queue()
        app.input_box, app.output_box = FakeWidget(), FakeWidget()
        return app

    def test_worker_result_reaches_completion_only_on_ui_poll_thread(self):
        app = self.fake_app()
        completed, worker_threads = [], []
        ui_thread = threading.get_ident()
        def operation():
            worker_threads.append(threading.get_ident())
            return 42
        app.run('test', operation, lambda result: completed.append((threading.get_ident(), result)))
        app.worker.join(timeout=2)
        self.assertFalse(app.worker.is_alive())
        self.assertEqual(completed, [])
        app.poll()
        self.assertEqual(completed, [(ui_thread, 42)])
        self.assertNotEqual(worker_threads, [ui_thread])
        self.assertIsNone(app.worker)

    def test_close_waits_for_non_daemon_worker_then_leaves_no_background(self):
        app = self.fake_app()
        release = threading.Event()
        app.run('recording', lambda: release.wait(2), lambda _: None)
        worker = app.worker
        self.assertFalse(worker.daemon)
        app.close()
        self.assertTrue(app.closing)
        self.assertFalse(app.root.destroyed)
        release.set()
        worker.join(timeout=2)
        app.poll()
        self.assertTrue(app.root.destroyed)
        self.assertFalse(worker.is_alive())
        self.assertIsNone(app.worker)


if __name__ == '__main__':
    unittest.main()
