"""Offline comparison. Run this on the Pi to obtain Pi evidence; host data is host data."""
import argparse
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import statistics
import time
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
from spake2 import SPAKE2_A, SPAKE2_B
from smartlock_protocol.v2 import SecureEnvelope, SecuritySession
from smartlock_protocol.v3 import Envelope, Session


def measure(function, iterations):
    samples = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        function()
        samples.append((time.perf_counter_ns()-start)/1000)
    samples.sort()
    return {'median_us': round(statistics.median(samples), 3),
            'p95_us': round(samples[min(len(samples)-1, int(len(samples)*.95))], 3), 'samples': iterations}


def pake():
    a, b = SPAKE2_A(b'offline-benchmark-only'), SPAKE2_B(b'offline-benchmark-only')
    msg_a, msg_b = a.start(), b.start()
    assert a.finish(msg_b) == b.finish(msg_a)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iterations', type=int, default=100)
    parser.add_argument('--output', type=Path, default=Path('releases/protocol-benchmark.json'))
    args = parser.parse_args()
    if not 1 <= args.iterations <= 10000:
        parser.error('iterations must be between 1 and 10000')
    key, aad = os.urandom(32), b'offline benchmark context'
    baseline = SecuritySession('baseline', 'benchmark', key, time.time()+3600)
    modern = Session('modern', 'benchmark', os.urandom(32), time.time()+3600, confirmed=True)
    results = []
    for size in (128, 4096, 65536):
        payload = os.urandom(size)
        business = {'image': base64.b64encode(payload).decode()}
        for name, function in (
            ('AES-GCM primitive', lambda: AESGCM(key).encrypt(os.urandom(12), payload, aad)),
            ('ChaCha20-Poly1305 primitive', lambda: ChaCha20Poly1305(key).encrypt(os.urandom(12), payload, aad)),
            ('v2 complete envelope', lambda: SecureEnvelope.seal(baseline, business)),
            ('v3 complete envelope', lambda: Envelope.seal(modern, business, endpoint='/api/secure/upload')),
        ):
            results.append({'name': name, 'input_bytes': size, **measure(function, args.iterations)})
    report = {'created_at': datetime.now(timezone.utc).isoformat(), 'machine': platform.machine(),
              'environment': platform.platform(), 'python': platform.python_version(),
              'scope': 'isolated host CPU microbenchmark; no camera, network, GPIO or Pi claims',
              'spake2_pair': measure(pake, min(args.iterations, 10)), 'results': results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(f'Offline benchmark saved: {args.output}; architecture={platform.machine()}')


if __name__ == '__main__':
    main()
