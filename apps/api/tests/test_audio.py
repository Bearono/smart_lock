import unittest
import numpy as np
from smartlock_protocol.audio import encode, decode, wav_bytes, read_wav


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
