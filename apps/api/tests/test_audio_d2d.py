"""D2D exchange, process restart, durable replay and key-at-rest regressions."""
from concurrent.futures import ThreadPoolExecutor
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

import numpy as np

from cryptography.hazmat.primitives.asymmetric import ec, rsa
from smartlock_protocol.audio_d2d import Peer, b64e, canonical, public_der
from smartlock_protocol import acoustic_fingerprint as fingerprint
from smartlock_protocol.audio import encode, wav_bytes

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('audio_peer_cli', ROOT / 'deploy/audio_peer.py')
audio_cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audio_cli)


class AudioD2DTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.now = 2000000000.0
        self.issuer = Peer(self.root / 'issuer', create=True, clock=lambda: self.now)
        self.receiver = Peer(self.root / 'receiver', create=True, clock=lambda: self.now)
        self.issuer_public = self.issuer.initialize('issuer', 'pi')
        self.receiver_public = self.receiver.initialize('receiver', 'phone')

    def exchange(self):
        request = self.receiver.create_request('pi')
        packet = self.issuer.issue(request, self.receiver_public)
        confirmation = self.receiver.accept(packet, self.issuer_public)
        return request, packet, confirmation

    def test_complete_exchange_requires_confirmation_and_rejects_replay_after_reopen(self):
        request, packet, confirmation = self.exchange()
        message = self.receiver.seal(request['session'], b'course message')
        with self.assertRaisesRegex(ValueError, 'unconfirmed'):
            self.issuer.open_message(message)
        self.issuer.verify_confirmation(confirmation)
        self.assertEqual(self.issuer.open_message(message), b'course message')
        reopened = Peer(self.root / 'issuer', clock=lambda: self.now)
        with self.assertRaisesRegex(ValueError, 'nonce already'):
            reopened.open_message(message)
        with self.assertRaisesRegex(ValueError, 'already consumed'):
            reopened.verify_confirmation(confirmation)
        reopened_receiver = Peer(self.root / 'receiver', clock=lambda: self.now)
        with self.assertRaisesRegex(ValueError, 'unused pending'):
            reopened_receiver.accept(packet, self.issuer_public)

    def test_pins_and_pending_challenge_are_enforced_before_acceptance(self):
        request = self.receiver.create_request('pi')
        other_receiver = public_der(rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key())
        with self.assertRaisesRegex(ValueError, 'pinned recipient'):
            self.issuer.issue(request, other_receiver)
        packet = self.issuer.issue(request, self.receiver_public)
        other_issuer = public_der(ec.generate_private_key(ec.SECP256R1()).public_key())
        with self.assertRaisesRegex(ValueError, 'signature'):
            self.receiver.accept(packet, other_issuer)
        altered = copy.deepcopy(packet)
        altered['binding']['challenge'] = 'a' * 32
        with self.assertRaisesRegex(ValueError, 'signature'):
            self.receiver.accept(altered, self.issuer_public)
        # A valid issuer signature still cannot substitute a different local pending challenge.
        changed_request = dict(request, session='b' * 32, challenge='c' * 32)
        changed_packet = self.issuer.issue(changed_request, self.receiver_public)
        with self.assertRaisesRegex(ValueError, 'unused pending'):
            self.receiver.accept(changed_packet, self.issuer_public)
        self.receiver.accept(packet, self.issuer_public)

    def test_tampered_confirm_message_and_expired_keys_fail_without_consuming_valid_message(self):
        request, _, confirmation = self.exchange()
        damaged = dict(confirmation, proof=b64e(b'wrong'))
        with self.assertRaises(ValueError):
            self.issuer.verify_confirmation(damaged)
        self.issuer.verify_confirmation(confirmation)
        message = self.receiver.seal(request['session'], b'hello')
        damaged = dict(message, ciphertext=b64e(b'X' * 21))
        with self.assertRaisesRegex(ValueError, 'authentication'):
            self.issuer.open_message(damaged)
        self.assertEqual(self.issuer.open_message(message), b'hello')
        self.now += 301
        with self.assertRaisesRegex(ValueError, 'Expired'):
            self.receiver.seal(request['session'], b'expired')

    def test_keys_are_encrypted_in_database_and_wrong_master_is_rejected(self):
        request, _, _ = self.exchange()
        with self.issuer.connect() as connection:
            _, key, _ = self.issuer.session(connection, request['session'], 'issuer')
            secret = connection.execute('SELECT secret FROM sessions').fetchone()[0]
        self.assertNotIn(key, secret)
        self.assertNotIn(key, self.issuer.database.read_bytes())
        private = self.issuer.local_value('private')
        self.assertNotIn(private, self.issuer.database.read_bytes())
        self.issuer.master_path.write_bytes(os.urandom(32))
        with self.assertRaisesRegex(ValueError, 'authentication failed'):
            Peer(self.root / 'issuer', clock=lambda: self.now).public_key()
        if os.name != 'nt':
            self.assertEqual(self.receiver.master_path.stat().st_mode & 0o777, 0o600)

    def test_concurrent_accept_and_message_delivery_have_one_winner(self):
        request = self.receiver.create_request('pi')
        packet = self.issuer.issue(request, self.receiver_public)

        def accept(_):
            try:
                return Peer(self.root / 'receiver', clock=lambda: self.now).accept(packet, self.issuer_public)
            except ValueError:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            accepted = list(pool.map(accept, range(2)))
        confirmations = [value for value in accepted if value is not None]
        self.assertEqual(len(confirmations), 1)
        self.issuer.verify_confirmation(confirmations[0])
        message = self.receiver.seal(request['session'], b'one delivery')

        def receive(_):
            try:
                return Peer(self.root / 'issuer', clock=lambda: self.now).open_message(message)
            except ValueError:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(receive, range(2)))
        self.assertEqual(results.count(b'one delivery'), 1)

    def test_strict_binding_and_single_direction(self):
        request = self.receiver.create_request('pi')
        for mutation in ({'expires': self.now + 1000}, {'challenge': 'wrong'}, {'version': 'old'}, {'extra': True}):
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.issuer.issue(dict(request, **mutation), self.receiver_public)
        with self.assertRaisesRegex(ValueError, 'peer role'):
            self.issuer.create_request('phone')

    def test_calibrated_same_wav_gate_is_applied_before_cli_cryptographic_acceptance(self):
        # Synthetic paths exercise integration, not microphone hardware identity accuracy.
        def recording(payload, seed, tap):
            samples = np.convolve(encode(payload), [1, tap], mode='full') * 0.4
            samples += np.random.default_rng(seed).normal(0, 0.00003, len(samples))
            return wav_bytes(np.concatenate((np.zeros(seed + 10), samples)))

        def model(tap, negative):
            payload = canonical({'scope': 'synthetic calibration fixture'})
            enrolled = fingerprint.enroll('phone', [recording(payload, seed, tap) for seed in range(3)])
            return fingerprint.calibrate(enrolled,
                                         [recording(payload, seed, tap) for seed in range(3, 7)],
                                         [recording(payload, seed, negative) for seed in range(7, 11)])

        self.now = time.time()
        request = self.receiver.create_request('pi')
        packet = self.issuer.issue(request, self.receiver_public)
        wave = self.root / 'delivered.wav'
        wave.write_bytes(recording(canonical(packet), 50, 0.10))
        good_model, wrong_model = self.root / 'good.json', self.root / 'wrong.json'
        good_model.write_text(json.dumps(model(0.10, 0.70)), encoding='utf-8')
        wrong_model.write_text(json.dumps(model(0.70, 0.40)), encoding='utf-8')
        self.assertEqual(audio_cli.read_packet(wave, good_model), packet)
        with self.assertRaisesRegex(ValueError, 'does not match'):
            audio_cli.read_packet(wave, wrong_model)
        public_key = self.root / 'issuer.der'
        public_key.write_bytes(self.issuer_public)
        confirmation = self.root / 'physical-gate-confirm.json'
        common = ['--state', str(self.root / 'receiver'), 'accept', '--input', str(wave),
                  '--issuer-public', str(public_key), '--output', str(confirmation)]
        with self.assertRaises(SystemExit) as rejection:
            audio_cli.main([*common, '--fingerprint-model', str(wrong_model)])
        self.assertEqual(rejection.exception.code, 2)
        self.assertFalse(confirmation.exists())
        self.assertEqual(audio_cli.main([*common, '--fingerprint-model', str(good_model)]), 0)
        self.issuer.verify_confirmation(json.loads(confirmation.read_text(encoding='utf-8')))

    def test_cli_independent_processes_wav_roundtrip_and_replay_rejection(self):
        environment = dict(os.environ, PYTHONPATH=str(ROOT / 'packages/smartlock_protocol') + os.pathsep + os.environ.get('PYTHONPATH', ''),
                           PYTHONDONTWRITEBYTECODE='1')
        cli_root = self.root / 'cli'
        cli_root.mkdir()

        def run(peer, *arguments, success=True):
            completed = subprocess.run([sys.executable, '-B', str(ROOT / 'deploy/audio_peer.py'),
                                        '--state', str(cli_root / peer), *map(str, arguments)],
                                       capture_output=True, text=True, env=environment, cwd=ROOT, timeout=20)
            if success:
                self.assertEqual(completed.returncode, 0, completed.stderr)
            else:
                self.assertNotEqual(completed.returncode, 0)
            return completed

        issuer_pub, receiver_pub = cli_root / 'issuer.der', cli_root / 'receiver.der'
        run('issuer', 'init-issuer', '--identity', 'pi', '--public-output', issuer_pub)
        run('receiver', 'init-receiver', '--identity', 'phone', '--public-output', receiver_pub)
        request, packet, confirm = cli_root / 'request.json', cli_root / 'packet.wav', cli_root / 'confirm.wav'
        run('receiver', 'request', '--sender', 'pi', '--output', request)
        session = json.loads(request.read_text())['session']
        run('issuer', 'issue', '--input', request, '--receiver-public', receiver_pub, '--output', packet)
        run('receiver', 'accept', '--input', packet, '--issuer-public', issuer_pub, '--output', confirm)
        run('issuer', 'confirm', '--input', confirm, '--output', cli_root / 'confirmed.json')
        plain, message = cli_root / 'input.txt', cli_root / 'message.wav'
        plain.write_bytes('Hello from phone / 课程消息'.encode())
        run('receiver', 'seal', '--session', session, '--input', plain, '--output', message)
        run('issuer', 'open', '--input', message, '--output', cli_root / 'output.txt')
        self.assertEqual((cli_root / 'output.txt').read_bytes(), plain.read_bytes())
        run('issuer', 'open', '--input', message, '--output', cli_root / 'replayed.txt', success=False)
        run('receiver', 'accept', '--input', packet, '--issuer-public', issuer_pub,
            '--output', cli_root / 'replayed-confirm.wav', success=False)
        run('issuer', 'init-issuer', '--identity', 'pi', '--public-output', issuer_pub, success=False)
        self.assertFalse((cli_root / 'replayed.txt').exists())


if __name__ == '__main__':
    unittest.main()
