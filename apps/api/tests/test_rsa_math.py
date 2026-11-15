"""Independent arithmetic, adversarial boundaries and vetted RSA cross-checks."""

import importlib.util
import math
from pathlib import Path
import random
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from smartlock_protocol.rsa_math import (
    decrypt_integer,
    encrypt_integer,
    extended_gcd,
    generate_keypair,
    generate_prime,
    is_probable_prime,
    key_from_primes,
    mod_exp,
    mod_inverse,
)


class RSAMathTests(unittest.TestCase):
    def test_square_and_multiply_matches_independent_builtin(self):
        rng = random.Random(20261115)
        cases = [(0, 0, 1), (0, 0, 7), (-4, 13, 497), (4, 13, 497)]
        cases += [
            (rng.randrange(-(1 << 256), 1 << 256), rng.getrandbits(128), rng.randrange(1, 1 << 256))
            for _ in range(40)
        ]
        for base, exponent, modulus in cases:
            self.assertEqual(mod_exp(base, exponent, modulus), pow(base, exponent, modulus))
        self.assertEqual(mod_exp(4, 13, 497), 445)

    def test_extended_gcd_signed_zero_and_known_coefficients(self):
        self.assertEqual(extended_gcd(4864, 3458), (38, 32, -45))
        for a, b in ((0, 0), (0, 7), (7, 0), (-240, 46), (240, -46), (-240, -46)):
            divisor, x, y = extended_gcd(a, b)
            self.assertEqual(divisor, math.gcd(a, b))
            self.assertEqual(a * x + b * y, divisor)

    def test_inverse_matches_builtin_and_rejects_non_coprimes(self):
        for value, modulus in ((17, 3120), (-17, 3120), (7, 26), (65537, 1000000006)):
            self.assertEqual(mod_inverse(value, modulus), pow(value, -1, modulus))
        for value, modulus in ((0, 17), (6, 15), (3, 1), (3, -1)):
            with self.assertRaises(ValueError):
                mod_inverse(value, modulus)

    def test_miller_rabin_primes_and_composites(self):
        # Exhaustive trial division is an independent oracle on the small domain.
        for candidate in range(-2, 1000):
            expected = candidate >= 2 and all(
                candidate % d for d in range(2, math.isqrt(candidate) + 1)
            )
            self.assertEqual(is_probable_prime(candidate, rounds=8), expected)
        for candidate in (561, 1105, 1729, 2465, 2821, 6601, 1009**2):
            self.assertFalse(is_probable_prime(candidate))
        self.assertTrue(is_probable_prime((1 << 127) - 1))

    def test_miller_rabin_uses_more_than_one_base_for_pseudoprimes(self):
        # 1373653 is strong probable-prime to bases 2 and 3, but not 5.
        with patch("smartlock_protocol.rsa_math.secrets.randbelow", side_effect=[0, 1, 3]) as draw:
            self.assertFalse(is_probable_prime(1373653, rounds=3))
        self.assertEqual(draw.call_count, 3)
        self.assertTrue(all(call.args == (1373650,) for call in draw.call_args_list))

    def test_prime_generation_exact_bits_and_exhaustion(self):
        for bits in (2, 16, 65):
            prime = generate_prime(bits)
            self.assertEqual(prime.bit_length(), bits)
            self.assertTrue(is_probable_prime(prime, rounds=40))
        with patch("smartlock_protocol.rsa_math.secrets.randbits", return_value=0):
            with self.assertRaises(RuntimeError):
                generate_prime(4, max_attempts=2)  # 9 is forced on both attempts.

    def test_known_textbook_rsa_vector_and_full_representative_domain(self):
        key = key_from_primes(61, 53, 17)
        self.assertEqual((key.n, key.d), (3233, 2753))
        self.assertEqual(encrypt_integer(65, key.n, key.e), 2790)
        self.assertEqual(decrypt_integer(2790, key.n, key.d), 65)
        for value in (0, 1, key.p, key.q, key.n - 1):
            self.assertEqual(
                decrypt_integer(encrypt_integer(value, key.n, key.e), key.n, key.d), value
            )
        self.assertNotIn(str(key.d), repr(key))
        self.assertNotIn(str(key.p), repr(key))

    def test_generated_key_imported_and_oaep_checked_by_vetted_library(self):
        # The manual key-generation path is checked by OpenSSL-backed validation
        # and OAEP; production is still forbidden from importing this module.
        key = generate_keypair(1024, rounds=32)
        self.assertEqual(key.n.bit_length(), 1024)
        private = rsa.RSAPrivateNumbers(
            p=key.p,
            q=key.q,
            d=key.d,
            dmp1=key.d % (key.p - 1),
            dmq1=key.d % (key.q - 1),
            iqmp=mod_inverse(key.q, key.p),
            public_numbers=rsa.RSAPublicNumbers(key.e, key.n),
        ).private_key()
        pad = padding.OAEP(
            mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=b"course-test"
        )
        ciphertext = private.public_key().encrypt(b"cross-check", pad)
        self.assertEqual(private.decrypt(ciphertext, pad), b"cross-check")

    def test_math_accepts_library_generated_parameters(self):
        numbers = rsa.generate_private_key(public_exponent=65537, key_size=1024).private_numbers()
        rebuilt = key_from_primes(numbers.p, numbers.q, numbers.public_numbers.e)
        self.assertEqual(rebuilt.n, numbers.public_numbers.n)
        for value in (0, 42, numbers.p, rebuilt.n - 1):
            cipher = encrypt_integer(value, rebuilt.n, rebuilt.e)
            self.assertEqual(cipher, pow(value, numbers.public_numbers.e, numbers.public_numbers.n))
            self.assertEqual(
                decrypt_integer(cipher, rebuilt.n, rebuilt.d), pow(cipher, numbers.d, rebuilt.n)
            )

    def test_invalid_input_is_rejected_without_coercion(self):
        bad_calls = (
            lambda: mod_exp(True, 3, 7),
            lambda: mod_exp(2, -1, 7),
            lambda: mod_exp(2, 3, 0),
            lambda: extended_gcd(3.0, 7),
            lambda: mod_inverse("3", 7),
            lambda: is_probable_prime(True),
            lambda: is_probable_prime(7, 0),
            lambda: is_probable_prime(7, True),
            lambda: is_probable_prime(1 << 4096),
            lambda: generate_prime(1),
            lambda: generate_prime(4097),
            lambda: generate_prime(16, max_attempts=0),
            lambda: generate_keypair(511),
            lambda: generate_keypair(1024, e=2),
            lambda: key_from_primes(61, 61, 17),
            lambda: key_from_primes(61, 55, 17),
            lambda: key_from_primes(61, 53, 15),
            lambda: encrypt_integer(-1, 3233, 17),
            lambda: encrypt_integer(3233, 3233, 17),
            lambda: encrypt_integer(42, 3233, 1),
            lambda: decrypt_integer(True, 3233, 2753),
            lambda: decrypt_integer(42, 3233, 0),
            lambda: decrypt_integer(42, 3232, 17),
        )
        for operation in bad_calls:
            with self.assertRaises(ValueError):
                operation()

    def test_report_records_actual_limits_and_no_key_material(self):
        script = Path(__file__).resolve().parents[3] / "deploy" / "rsa_math_lab.py"
        spec = importlib.util.spec_from_file_location("rsa_math_lab_test", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        report = module.run(bits=512, rounds=16, iterations=2)
        self.assertTrue(report["passed"])
        self.assertFalse(report["security"]["safe_for_production"])
        self.assertTrue(report["checks"]["raw_rsa_is_malleable"])
        self.assertEqual(report["timings"]["key_generation"]["samples"], 1)
        self.assertEqual(report["timings"]["textbook_decrypt"]["samples"], 2)

        def inspect(value):
            if isinstance(value, dict):
                self.assertTrue(
                    set(value).isdisjoint(
                        {"p", "q", "d", "n", "private_key", "plaintext", "ciphertext"}
                    )
                )
                for child in value.values():
                    inspect(child)
            elif isinstance(value, list):
                for child in value:
                    inspect(child)

        inspect(report)


if __name__ == "__main__":
    unittest.main()
