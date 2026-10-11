"""Explicit course experiments. Never used by the production command channel.

XXTEA is an unauthenticated teaching primitive. X25519 here demonstrates DH,
not peer authentication. The running device continues to use confirmed SPAKE2
and AES-GCM. Reports contain outcomes and timings, never keys or face data.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import struct
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa, x25519
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

MASK = 0xffffffff
DELTA = 0x9e3779b9


def xxtea_words(words, key, *, decrypt=False):
    """Corrected Block TEA on 2..4096 uint32 words with a 128-bit key.

    Word framing is explicit; no ambiguous zero padding or integrity claims.
    Reject bool, negative and overflowing inputs instead of silently truncating.
    """
    values, key = list(words), list(key)
    if not 2 <= len(values) <= 4096 or len(key) != 4:
        raise ValueError('Expected 2..4096 words and four key words')
    if any(type(v) is not int or not 0 <= v <= MASK for v in values + key):
        raise ValueError('Words must be unsigned 32-bit integers')
    n = len(values)
    rounds = 6 + 52 // n

    def mix(z, y, total, p, e):
        return (((z >> 5 ^ y << 2) + (y >> 3 ^ z << 4)) ^
                ((total ^ y) + (key[(p & 3) ^ e] ^ z))) & MASK

    if decrypt:
        total, y = (rounds * DELTA) & MASK, values[0]
        for _ in range(rounds):
            e = total >> 2 & 3
            for p in range(n - 1, 0, -1):
                values[p] = (values[p] - mix(values[p - 1], y, total, p, e)) & MASK
                y = values[p]
            values[0] = (values[0] - mix(values[-1], y, total, 0, e)) & MASK
            y = values[0]
            total = (total - DELTA) & MASK
    else:
        total, z = 0, values[-1]
        for _ in range(rounds):
            total = (total + DELTA) & MASK
            e = total >> 2 & 3
            for p in range(n - 1):
                values[p] = (values[p] + mix(z, values[p + 1], total, p, e)) & MASK
                z = values[p]
            values[-1] = (values[-1] + mix(z, values[0], total, n - 1, e)) & MASK
            z = values[-1]
    return tuple(values)


def oaep():
    return padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(),
                        label=b'smart-lock/course/key-wrap/v1')


def verify_ecdsa(public_key, message, signature):
    try:
        public_key.verify(signature, message, ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError):
        return False


def dh_key(private_key, public_key, context):
    if not isinstance(context, bytes) or not context:
        raise ValueError('A nonempty exchange context is required')
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                info=b'smart-lock/course/dh/v1\0' + context).derive(private_key.exchange(public_key))


def run_experiments():
    started = time.perf_counter()
    report = {'created_at': datetime.now(timezone.utc).isoformat(),
              'platform': platform.platform(), 'architecture': platform.machine(),
              'python': platform.python_version(),
              'scope': 'isolated course primitives; not an authenticated D2D or KDC integration',
              'results': {}}
    values = tuple(range(32))
    tea_key = struct.unpack('<4I', os.urandom(16))
    encrypted = xxtea_words(values, tea_key)
    report['results']['XXTEA'] = {
        'roundtrip': xxtea_words(encrypted, tea_key, decrypt=True) == values,
        'integrity_provided': False, 'input_bytes': len(values) * 4}
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    secret = os.urandom(32)
    wrapped = key.public_key().encrypt(secret, oaep())
    report['results']['RSA-OAEP-SHA256'] = {'key_bits': key.key_size,
                                          'roundtrip': key.decrypt(wrapped, oaep()) == secret}
    signer = ec.generate_private_key(ec.SECP256R1())
    message = b'course identity and context binding'
    signature = signer.sign(message, ec.ECDSA(hashes.SHA256()))
    report['results']['ECDSA-P256-SHA256'] = {
        'valid_signature': verify_ecdsa(signer.public_key(), message, signature),
        'tamper_rejected': not verify_ecdsa(signer.public_key(), message + b'!', signature)}
    alice, bob = x25519.X25519PrivateKey.generate(), x25519.X25519PrivateKey.generate()
    context = os.urandom(32)
    report['results']['X25519-HKDF-SHA256'] = {
        'shared_key_agrees': dh_key(alice, bob.public_key(), context) == dh_key(bob, alice.public_key(), context),
        'context_separated': dh_key(alice, bob.public_key(), context) != dh_key(alice, bob.public_key(), context + b'!'),
        'peer_authentication_provided': False}
    report['seconds'] = round(time.perf_counter() - started, 4)
    required = ('roundtrip', 'valid_signature', 'tamper_rejected', 'shared_key_agrees', 'context_separated')
    report['passed'] = all(value for row in report['results'].values() for name, value in row.items() if name in required)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run_experiments()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
