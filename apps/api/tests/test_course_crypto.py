"""Course primitives are tested independently of device authorization."""
import unittest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, rsa, x25519
from smartlock_protocol.course_lab import xxtea_words, verify_ecdsa, dh_key, oaep, run_experiments


class CourseCryptoTests(unittest.TestCase):
    def test_xxtea_matches_independent_uint32_c_reference(self):
        # Word vectors cross-checked with an independently compiled uint32 C
        # implementation using xxtea-c's round order and mixing formula.
        for plaintext, key, ciphertext in (
            ((0, 0), (0, 0, 0, 0), (0x053704ab, 0x575d8c80)),
            ((0, 1, 2, 3), (0, 1, 2, 3),
             (0x3419501e, 0x9c1ef12d, 0x694842e0, 0x70918bb8)),
        ):
            self.assertEqual(xxtea_words(plaintext, key), ciphertext)
            self.assertEqual(xxtea_words(ciphertext, key, decrypt=True), plaintext)

    def test_xxtea_sizes_and_input_are_not_mutated(self):
        for count in (2, 3, 32, 64):
            values = list(range(count))
            ciphertext = xxtea_words(values, [0, 1, 2, 3])
            self.assertEqual(xxtea_words(ciphertext, [0, 1, 2, 3], decrypt=True), tuple(values))
            self.assertEqual(values, list(range(count)))
            self.assertNotEqual(ciphertext, tuple(values))

    def test_xxtea_rejects_invalid_words(self):
        for values in ([1], [True, 0], [-1, 0], [2 ** 32, 0], [0] * 4097):
            with self.assertRaises(ValueError):
                xxtea_words(values, [0] * 4)
        with self.assertRaises(ValueError):
            xxtea_words([0, 0], [0] * 3)

    def test_ecdsa_rejects_other_identity_and_modified_message(self):
        key = ec.generate_private_key(ec.SECP256R1())
        other = ec.generate_private_key(ec.SECP256R1())
        signature = key.sign(b'message', ec.ECDSA(hashes.SHA256()))
        self.assertTrue(verify_ecdsa(key.public_key(), b'message', signature))
        self.assertFalse(verify_ecdsa(other.public_key(), b'message', signature))
        self.assertFalse(verify_ecdsa(key.public_key(), b'changed', signature))
        self.assertFalse(verify_ecdsa(key.public_key(), b'message', b'invalid DER'))

    def test_rsa_wrong_key_and_corrupted_ciphertext_are_rejected(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        ciphertext = key.public_key().encrypt(b'course key', oaep())
        self.assertEqual(key.decrypt(ciphertext, oaep()), b'course key')
        with self.assertRaises(ValueError):
            other.decrypt(ciphertext, oaep())
        with self.assertRaises(ValueError):
            key.decrypt(ciphertext[:-1], oaep())

    def test_dh_context_and_zero_public_key(self):
        a, b = x25519.X25519PrivateKey.generate(), x25519.X25519PrivateKey.generate()
        self.assertEqual(dh_key(a, b.public_key(), b'context'), dh_key(b, a.public_key(), b'context'))
        self.assertNotEqual(dh_key(a, b.public_key(), b'context'), dh_key(a, b.public_key(), b'other'))
        with self.assertRaises(ValueError):
            dh_key(a, x25519.X25519PublicKey.from_public_bytes(bytes(32)), b'context')
        with self.assertRaises(ValueError):
            dh_key(a, b.public_key(), b'')

    def test_report_contains_no_private_material(self):
        report = run_experiments()
        self.assertTrue(report['passed'])
        self.assertFalse(report['results']['XXTEA']['integrity_provided'])
        self.assertFalse(report['results']['X25519-HKDF-SHA256']['peer_authentication_provided'])
        self.assertNotIn('private_key', report)
