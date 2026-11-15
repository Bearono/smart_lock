"""Run isolated RSA arithmetic and export only checks, parameters and timings.

No keys, prime factors, plaintexts or ciphertexts are exported. This script
does not connect to the backend or device, and does not change their protocol.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import statistics
import time

from smartlock_protocol.rsa_math import (
    decrypt_integer, encrypt_integer, extended_gcd, generate_keypair,
    is_probable_prime, key_from_primes, mod_inverse,
)


def measure(operation, iterations):
    operation()
    samples = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        operation()
        samples.append((time.perf_counter_ns() - start) / 1000)
    samples.sort()
    return {'samples': len(samples), 'median_us': round(statistics.median(samples), 3),
            'p95_us': round(samples[(95 * len(samples) + 99) // 100 - 1], 3)}


def run(bits=1024, rounds=32, iterations=10):
    if type(iterations) is not int or not 1 <= iterations <= 100:
        raise ValueError('Use 1..100 timing iterations')
    start = time.perf_counter_ns()
    key = generate_keypair(bits, rounds=rounds)
    generation_us = (time.perf_counter_ns() - start) / 1000
    toy = key_from_primes(61, 53, 17)
    message = 42
    encrypted = encrypt_integer(message, key.n, key.e)
    # These checks expose why raw RSA must not replace a padded encryption scheme.
    multiplied = encrypted * encrypt_integer(2, key.n, key.e) % key.n
    cases = (0, 1, message, key.p, key.q, key.n - 1)
    checks = {
        'known_rsa_vector': toy.n == 3233 and toy.d == 2753
            and encrypt_integer(65, toy.n, toy.e) == 2790
            and decrypt_integer(2790, toy.n, toy.d) == 65,
        'bezout_identity': extended_gcd(4864, 3458) == (38, 32, -45),
        'inverse_reference': mod_inverse(17, 3120) == 2753,
        'roundtrip_including_non_coprime_representatives': all(
            decrypt_integer(encrypt_integer(value, key.n, key.e), key.n, key.d) == value
            for value in cases),
        'builtin_pow_agrees': encrypted == pow(message, key.e, key.n)
            and decrypt_integer(encrypted, key.n, key.d) == pow(encrypted, key.d, key.n),
        'exact_modulus_bits': key.n.bit_length() == bits,
        'raw_rsa_is_deterministic': encrypt_integer(message, key.n, key.e) == encrypted,
        'raw_rsa_is_malleable': decrypt_integer(multiplied, key.n, key.d) == message * 2,
    }
    timings = {
        'key_generation': {'samples': 1, 'elapsed_us': round(generation_us, 3)},
        'miller_rabin_on_generated_prime': measure(lambda: is_probable_prime(key.p, rounds), iterations),
        'extended_euclid': measure(lambda: extended_gcd(key.e, (key.p - 1) * (key.q - 1)), iterations),
        'modular_inverse': measure(lambda: mod_inverse(key.e, (key.p - 1) * (key.q - 1)), iterations),
        'textbook_encrypt': measure(lambda: encrypt_integer(message, key.n, key.e), iterations),
        'textbook_decrypt': measure(lambda: decrypt_integer(encrypted, key.n, key.d), iterations),
        'builtin_pow_same_public_operation': measure(lambda: pow(message, key.e, key.n), iterations),
        'builtin_pow_same_private_operation': measure(lambda: pow(encrypted, key.d, key.n), iterations),
    }
    return {
        'created_at': datetime.now(timezone.utc).isoformat(),
        'environment': platform.platform(), 'architecture': platform.machine(),
        'python': platform.python_version(), 'modulus_bits': bits,
        'public_exponent': key.e, 'miller_rabin_rounds': rounds,
        'fixed_odd_composite_false_positive_bound': f'4^-{rounds}; independently random bases only',
        'scope': 'isolated variable-time textbook RSA; no production, network or hardware claims',
        'security': {'safe_for_production': False, 'padding': False,
                     'constant_time': False, 'blinding': False,
                     'primality_proof': False, 'authentication': False},
        'principles': [
            'Square-and-multiply scans exponent bits and reduces after every product.',
            'Extended Euclid produces Bezout coefficients; a coprime coefficient is the inverse.',
            'Miller-Rabin tests random bases against the odd part of candidate minus one.',
            'RSA derives d as the inverse of e modulo (p-1)*(q-1).',
            'Textbook determinism and multiplicativity demonstrate missing encryption security.',
        ],
        'sources': [
            'https://cacr.uwaterloo.ca/hac/about/chap2.pdf',
            'https://cacr.uwaterloo.ca/hac/about/chap4.pdf',
            'https://cacr.uwaterloo.ca/hac/about/chap8.pdf',
            'https://www.rfc-editor.org/rfc/rfc8017.html',
        ],
        'checks': checks, 'timings': timings, 'passed': all(checks.values()),
        'measurement_limits': 'CPU only; one key-generation sample; Python pow is a runtime comparison, not an algorithm security ranking.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bits', type=int, default=1024)
    parser.add_argument('--rounds', type=int, default=32)
    parser.add_argument('--iterations', type=int, default=10)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output exists; choose a new trial filename')
    try:
        report = run(args.bits, args.rounds, args.iterations)
    except ValueError as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
