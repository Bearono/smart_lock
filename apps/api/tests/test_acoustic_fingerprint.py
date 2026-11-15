"""Synthetic algorithm checks, never acoustic hardware accuracy evidence."""
import importlib.util
from pathlib import Path
import tempfile
import struct
import unittest

import numpy as np

from smartlock_protocol import acoustic_fingerprint as af
from smartlock_protocol.audio import _encode_legacy, analyze, decode, encode, read_wav, wav_bytes

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('course_audio_device', ROOT / 'deploy/audio_device.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def recording(seed, other=False):
    values = encode(b'known-challenge-0123456789')
    tap = 0.70 if other else 0.10
    values = np.convolve(values, [1, tap], mode='full') * 0.4
    values += np.random.default_rng(seed).normal(0, 0.00003, len(values))
    return wav_bytes(np.concatenate((np.zeros(seed + 10), values)))


class AcousticFingerprintTests(unittest.TestCase):
    def test_analysis_preserves_original_wire_decode(self):
        wave = recording(1)
        result = analyze(read_wav(wave))
        self.assertEqual(result['payload'], b'known-challenge-0123456789')
        self.assertEqual(decode(read_wav(wave)), result['payload'])
        self.assertGreater(result['sync_score'], 0.6)
        self.assertEqual(result['channel'].shape, (64,))

    def test_requires_multiple_unique_enrollment_recordings(self):
        one = recording(1)
        for recordings in ([one], [one, one, one]):
            with self.assertRaises(ValueError):
                af.enroll('phone_01', recordings)
        with self.assertRaises(ValueError):
            af.enroll('../phone', [recording(i) for i in range(3)])

    def test_enrollment_cannot_authorize_before_calibration(self):
        template = af.enroll('phone_01', [recording(i) for i in range(3)])
        with self.assertRaises(ValueError):
            af.verify(template, recording(7))

    def test_calibration_evaluation_and_challenge_binding(self):
        template = af.enroll('phone_01', [recording(i) for i in range(3)])
        calibrated = af.calibrate(template, [recording(i) for i in range(3, 7)],
                                  [recording(i, True) for i in range(7, 11)])
        self.assertIsNone(template['threshold'])
        self.assertGreater(calibrated['threshold'], max(calibrated['calibration']['genuine_distances']))
        self.assertLess(calibrated['threshold'], min(calibrated['calibration']['impostor_distances']))
        accepted = af.verify(calibrated, recording(20), b'known-challenge-0123456789')
        self.assertTrue(accepted['matched'])
        self.assertFalse(accepted['cryptographic_identity_verified'])
        self.assertFalse(af.verify(calibrated, recording(21, True))['matched'])
        with self.assertRaises(ValueError):
            af.verify(calibrated, recording(20), b'a-new-challenge')
        report = af.evaluate(calibrated, [recording(i) for i in range(22, 26)],
                             [recording(i, True) for i in range(26, 30)])
        self.assertEqual(report['genuine_count'], 4)
        self.assertEqual(report['impostor_count'], 4)
        self.assertEqual(report['far'], 0)

    def test_transport_profiles_cannot_share_calibration(self):
        legacy = wav_bytes(_encode_legacy(b'known-challenge-0123456789') * 0.4)
        with self.assertRaisesRegex(ValueError, 'transport profile'):
            af.enroll('phone', [recording(1), recording(2), legacy])
        template = af.enroll('phone', [recording(i) for i in range(3)])
        with self.assertRaisesRegex(ValueError, 'transport profile'):
            af._scored(template, [legacy], minimum=1)

    def test_clipping_check_applies_to_decoded_frame(self):
        values = read_wav(recording(1))
        clean = af.extract(wav_bytes(values))
        outside = af.extract(wav_bytes(np.concatenate((np.ones(1000), np.zeros(2000), values))))
        self.assertEqual(clean['payload_sha256'], outside['payload_sha256'])
        # A valid legacy frame retains its decodability with saturated guard samples.
        clipped = _encode_legacy(b'known-challenge-0123456789') * 0.4
        clipped[650:670] = 1
        with self.assertRaisesRegex(ValueError, 'Clipped'):
            af.extract(wav_bytes(clipped))

    def test_rejects_data_leakage_between_sets(self):
        enrolled = [recording(i) for i in range(3)]
        positive = [recording(i) for i in range(3, 6)]
        negative = [recording(i, True) for i in range(6, 9)]
        template = af.enroll('phone', enrolled)
        with self.assertRaises(ValueError):
            af.calibrate(template, enrolled, negative)
        calibrated = af.calibrate(template, positive, negative)
        with self.assertRaises(ValueError):
            af.evaluate(calibrated, positive, [recording(i, True) for i in range(12, 15)])

    def test_riff_metadata_cannot_disguise_a_reused_recording(self):
        original = recording(1)
        altered = original + b'JUNK' + struct.pack('<I', 4) + b'test'
        altered = altered[:4] + struct.pack('<I', len(altered) - 8) + altered[8:]
        first, second = af.extract(original), af.extract(altered)
        self.assertNotEqual(first['source_file_sha256'], second['source_file_sha256'])
        self.assertEqual(first['recording_sha256'], second['recording_sha256'])
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            af.enroll('phone', [original, altered, recording(2)])

    def test_bad_audio_model_and_far_rejected(self):
        with self.assertRaises(ValueError):
            af.extract(wav_bytes(np.ones(3000)))
        with self.assertRaises(ValueError):
            af.extract(wav_bytes(np.zeros(3000)))
        with self.assertRaises(ValueError):
            af.distance({'version': 'other'}, [0] * 64)
        template = af.enroll('phone', [recording(i) for i in range(3)])
        for target in (-1, float('nan'), True, 1):
            with self.assertRaises(ValueError):
                af.calibrate(template, [], [], target)

    def test_audio_cli_file_roundtrip_and_exclusive_output(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            payload, wave, recovered = (folder / name for name in ('message.bin', 'frame.wav', 'decoded.bin'))
            payload.write_bytes(b'course D2D payload')
            self.assertEqual(cli.main(['encode', '--input', str(payload), '--output', str(wave)]), 0)
            self.assertEqual(cli.main(['decode', '--input', str(wave), '--output', str(recovered)]), 0)
            self.assertEqual(payload.read_bytes(), recovered.read_bytes())
            with self.assertRaises(FileExistsError):
                cli.main(['decode', '--input', str(wave), '--output', str(recovered)])

    def test_hardware_io_requires_explicit_device_and_bounds(self):
        for duration in (-1, 0, 11, float('nan'), True):
            with self.assertRaises(ValueError):
                cli.record(duration, 0)
        with self.assertRaises(ValueError):
            cli.record(1, None)
        for gain in (0, 1, float('inf'), True):
            with self.assertRaises(ValueError):
                cli.play(recording(1), 0, gain)
        with self.assertRaises(ValueError):
            cli.play(recording(1), None)

    def test_device_listing_accepts_native_index_field(self):
        class DeviceBackend:
            def query_devices(self):
                return [{'index': 0, 'name': 'explicit test input', 'max_input_channels': 1, 'hostapi': 0}]

            def query_hostapis(self, index):
                return {'name': 'test host API'}
        self.assertEqual(cli.list_devices(DeviceBackend())[0]['index'], 0)


if __name__ == '__main__':
    unittest.main()
