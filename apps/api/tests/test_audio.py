import unittest
import numpy as np
from smartlock_protocol.audio import encode, decode, wav_bytes, read_wav, _encode_legacy, analyze


class AudioTests(unittest.TestCase):
    def test_pcm_binary_roundtrip_and_lengths(self):
        for payload in (b'hello', bytes(range(256)), b'x' * 2048):
            self.assertEqual(decode(read_wav(wav_bytes(encode(payload)))), payload)

    def test_delay_noise_gain_polarity_and_short_multipath(self):
        payload = bytes(range(128))
        original = encode(payload)
        channel = np.convolve(original, [0.7] + [0] * 7 + [0.15])
        noise = np.random.default_rng(42).normal(0, 0.002, len(channel))
        recording = np.concatenate((np.zeros(273), -(channel + noise) * 0.5, np.zeros(137)))
        self.assertEqual(decode(recording), payload)

    def test_truncation_damage_and_silence_are_rejected(self):
        frame = encode(b'x' * 256)
        for values in (frame[:700], np.zeros(3000), np.full(3000, np.nan)):
            with self.assertRaises(ValueError):
                decode(values)
        frame[1000:2000] = np.random.default_rng(1).normal(0, 0.3, 1000)
        with self.assertRaises(ValueError):
            decode(frame)

    def test_bounds(self):
        for payload in (b'', b'a' * 2049, 'text'):
            with self.assertRaises(ValueError):
                encode(payload)
        with self.assertRaises(ValueError):
            wav_bytes(np.array([2.0]))

    def test_old_wav_files_still_decode_and_new_frames_fit_ten_seconds(self):
        payload = bytes(range(128))
        self.assertEqual(decode(wav_bytes_values := read_wav(wav_bytes(_encode_legacy(payload)))), payload)
        self.assertEqual(analyze(wav_bytes_values)['profile'], 'SL-OFDM-1')
        self.assertLessEqual(len(encode(b'x' * 2048)), 480000)
        self.assertEqual(analyze(encode(payload))['profile'], 'SL-OFDM-2')

    def test_room_echo_exceeding_legacy_guard_interval(self):
        payload = bytes(range(256))
        impulse = np.zeros(180)
        impulse[0], impulse[81], impulse[173] = .65, -.48, .27
        values = np.convolve(encode(payload), impulse)
        values += np.random.default_rng(913).normal(0, .001, len(values))
        self.assertEqual(decode(np.r_[np.zeros(509), values * .4]), payload)

    def test_frequency_notches_can_erase_one_copy_without_changing_payload(self):
        # Three narrow notches in a linear acoustic response, independent of packet bits.
        impulse = np.array([1.])
        for frequency in (4125, 6000, 10312.5):
            impulse = np.convolve(impulse, [1., -2 * np.cos(2 * np.pi * frequency / 48000), 1.])
        impulse /= np.linalg.norm(impulse)
        payload = bytes((i * 53) % 256 for i in range(200))
        values = np.convolve(encode(payload), impulse)
        self.assertEqual(decode(np.r_[np.zeros(139), values]), payload)

    def test_long_frame_with_independent_sampling_clock_drift(self):
        payload = bytes((i * 53) % 256 for i in range(1536))
        impulse = np.zeros(90)
        impulse[0], impulse[81] = .7, .18
        original = np.convolve(encode(payload), impulse)
        for ppm in (-100, -50, 50, 100):
            factor = 1 + ppm / 1e6
            recording = np.interp(np.arange(int(len(original) * factor)) / factor,
                                  np.arange(len(original)), original)
            recording += np.random.default_rng(ppm + 101).normal(0, .0001, len(recording))
            self.assertEqual(decode(np.r_[np.zeros(301), recording, np.zeros(100)]), payload)
