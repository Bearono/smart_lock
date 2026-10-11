"""Bounded local CPU experiments; no network, camera or biometric material."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import statistics
import time

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, rsa, x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from smartlock_protocol.course_lab import xxtea_words, oaep, dh_key
from smartlock_protocol.distribution_lab import Recipient, kdc_pair, public_packet


def measure(operation, iterations):
    operation()  # Untimed warm-up; do not include initialization in steady state.
    samples = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        operation()
        samples.append((time.perf_counter_ns() - start) / 1000)
    samples.sort()
    return {'samples': iterations, 'median_us': round(statistics.median(samples), 3),
            'p95_us': round(samples[max(0, (95 * len(samples) + 99) // 100 - 1)], 3)}


def benchmark(iterations):
    if type(iterations) is not int or not 5 <= iterations <= 200:
        raise ValueError('Use 5..200 iterations')
    results = []

    def add(name, operation, size=None, count=None):
        row = {'operation': name, **measure(operation, count or iterations)}
        if size is not None:
            row['input_bytes'] = size
        results.append(row)

    key = os.urandom(32)
    tea_key = (0x1a2b3c4d, 0x54657687, 0x98a9bacb, 0xdcedfe0f)
    cipher = AESGCM(key)
    for size in (128, 4096, 16384):
        values = tuple(range(size // 4))
        encoded = xxtea_words(values, tea_key)
        add('XXTEA encrypt (Python, unauthenticated)', lambda: xxtea_words(values, tea_key), size)
        add('XXTEA decrypt (Python, unauthenticated)', lambda: xxtea_words(encoded, tea_key, decrypt=True), size)
        payload, nonce = os.urandom(size), os.urandom(12)
        ciphertext = cipher.encrypt(nonce, payload, b'course benchmark')
        add('AES-256-GCM encrypt (native AEAD)',
            lambda: cipher.encrypt(os.urandom(12), payload, b'course benchmark'), size)
        add('AES-256-GCM decrypt (native AEAD)',
            lambda: cipher.decrypt(nonce, ciphertext, b'course benchmark'), size)
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public, secret = private.public_key(), os.urandom(32)
    wrapped = public.encrypt(secret, oaep())
    add('RSA-2048 OAEP wrap', lambda: public.encrypt(secret, oaep()), 32)
    add('RSA-2048 OAEP unwrap', lambda: private.decrypt(wrapped, oaep()), 32)
    add('RSA-2048 key generation',
        lambda: rsa.generate_private_key(public_exponent=65537, key_size=2048), count=min(iterations, 10))
    signer = ec.generate_private_key(ec.SECP256R1())
    message = os.urandom(128)
    signature = signer.sign(message, ec.ECDSA(hashes.SHA256()))
    add('ECDSA-P256 sign', lambda: signer.sign(message, ec.ECDSA(hashes.SHA256())), 128)
    add('ECDSA-P256 verify', lambda: signer.public_key().verify(signature, message, ec.ECDSA(hashes.SHA256())), 128)
    alice, bob = x25519.X25519PrivateKey.generate(), x25519.X25519PrivateKey.generate()
    add('X25519 exchange + HKDF-SHA256', lambda: dh_key(alice, bob.public_key(), b'course benchmark'))
    registered = {name: os.urandom(32) for name in ('alice', 'bob')}

    def kdc_exchange():
        session, tickets = kdc_pair(registered, 'alice', 'bob')
        a = Recipient('alice').receive_kdc(tickets[0], registered['alice'], 'bob', session)
        b = Recipient('bob').receive_kdc(tickets[1], registered['bob'], 'alice', session)
        assert a == b

    def public_distribution():
        session, secret = os.urandom(16).hex(), os.urandom(32)
        packet = public_packet('alice', 'bob', public, signer, session, secret)
        assert Recipient('bob').receive_public(packet, private, signer.public_key(), 'alice', session) == secret

    add('KDC issue + two ticket decryptions (in-memory lab)', kdc_exchange)
    add('RSA + ECDSA key delivery (in-memory lab)', public_distribution)
    return {'created_at': datetime.now(timezone.utc).isoformat(), 'architecture': platform.machine(),
            'environment': platform.platform(), 'python': platform.python_version(),
            'scope': 'local CPU microbenchmark; excludes network, camera and full handshake',
            'comparison_limit': 'Python XXTEA versus native AEAD is not an equal-language algorithm ranking',
            'results': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iterations', type=int, default=50)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 5 <= args.iterations <= 200:
        parser.error('iterations must be between 5 and 200')
    report = benchmark(args.iterations)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2)
    print(f'CPU experiment saved: {args.output}; architecture={platform.machine()}')


if __name__ == '__main__':
    main()
