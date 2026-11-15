"""Exercise the actual Java and Python OFDM implementations in both directions."""
import argparse
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'packages/smartlock_protocol'))
import numpy as np
from smartlock_protocol.audio import encode, decode, wav_bytes, read_wav, _encode_legacy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--java', default='java')
    parser.add_argument('--classes', default=str(ROOT / 'examples/android_audio/build/jvm-test'))
    args = parser.parse_args()
    count = 0
    with TemporaryDirectory() as directory:
        directory = Path(directory)

        def java(action, source, target):
            subprocess.run([args.java, '-cp', args.classes, 'CodecInterop', action,
                            str(source), str(target)], check=True, capture_output=True, timeout=30)

        for size in (1, 5, 256, 2048):
            payload = bytes((i * 37 + size) % 256 for i in range(size))
            original = directory / 'original.bin'
            python_wave = directory / 'python.wav'
            java_wave = directory / 'java.wav'
            recovered = directory / 'recovered.bin'
            original.write_bytes(payload)
            python_wave.write_bytes(wav_bytes(encode(payload)))
            java('decode', python_wave, recovered)
            assert recovered.read_bytes() == payload, f'Python → Java failed: {size}'
            java('encode', original, java_wave)
            assert decode(read_wav(java_wave.read_bytes())) == payload, f'Java → Python failed: {size}'
            # PCM vectors should agree within one least-significant sample after rounding.
            left, right = read_wav(python_wave.read_bytes()), read_wav(java_wave.read_bytes())
            assert left.shape == right.shape
            assert np.max(np.abs(left - right)) <= 1.01 / 32767
            count += 3

        payload = bytes(range(128))
        channel = np.convolve(encode(payload), [0.7] + [0] * 7 + [0.15])
        noise = np.random.default_rng(42).normal(0, 0.002, len(channel))
        delayed = np.concatenate((np.zeros(273), -(channel + noise) * 0.5, np.zeros(137)))
        python_wave.write_bytes(wav_bytes(delayed))
        java('decode', python_wave, recovered)
        assert recovered.read_bytes() == payload, 'Python noisy channel → Java failed'
        count += 1
        python_wave.write_bytes(wav_bytes(_encode_legacy(payload)))
        java('decode', python_wave, recovered)
        assert recovered.read_bytes() == payload, 'Legacy SLA1 → Java failed'
        count += 1
        payload = bytes((i * 53) % 256 for i in range(1536))
        impulse = np.zeros(90)
        impulse[0], impulse[81] = .7, .18
        channel = np.convolve(encode(payload), impulse)
        for ppm in (-100, -50, 50, 100):
            factor = 1 + ppm / 1e6
            drifted = np.interp(np.arange(int(len(channel) * factor)) / factor,
                                np.arange(len(channel)), channel)
            drifted += np.random.default_rng(ppm + 101).normal(0, .0001, len(drifted))
            python_wave.write_bytes(wav_bytes(np.r_[np.zeros(301), drifted, np.zeros(100)]))
            java('decode', python_wave, recovered)
            assert recovered.read_bytes() == payload, f'Clock drift → Java failed: {ppm} ppm'
            count += 1
    print(f'PASS: {count} bidirectional codec/vector/channel checks')


if __name__ == '__main__':
    main()
