"""Verify certificate identities and refusal to replace installed TLS material."""
import importlib.util
import ipaddress
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import serialization

ROOT = Path(__file__).resolve().parents[3]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'deploy' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TLSDeliveryTests(unittest.TestCase):
    def test_distinct_device_identity_signed_by_ca_and_no_overwrite(self):
        initial, issuer = load('init_local_tls'), load('issue_device_tls')
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / 'deploy/tls'
            try:
                with patch.object(initial, 'ROOT', root), patch('sys.argv', ['init_local_tls']):
                    initial.main()
                with patch.object(issuer, 'ROOT', root), patch('sys.argv', ['issue_device_tls', '--host', '192.168.1.20']):
                    issuer.main()
                    saved = (directory / 'device.key').read_bytes()
                    with self.assertRaises(SystemExit):
                        issuer.main()
                    self.assertEqual(saved, (directory / 'device.key').read_bytes())
                ca = x509.load_pem_x509_certificate((directory / 'ca.crt').read_bytes())
                device = x509.load_pem_x509_certificate((directory / 'device.crt').read_bytes())
                server = x509.load_pem_x509_certificate((directory / 'server.crt').read_bytes())
                device.verify_directly_issued_by(ca)
                san = device.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
                self.assertEqual(san.get_values_for_type(x509.IPAddress), [ipaddress.ip_address('192.168.1.20')])
                encoding, form = serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
                self.assertNotEqual(device.public_key().public_bytes(encoding, form), server.public_key().public_bytes(encoding, form))
                self.assertLessEqual(device.not_valid_after_utc, ca.not_valid_after_utc)
            finally:
                # Windows also treats chmod's read-only flag as a deletion restriction.
                for file in directory.glob('*'):
                    os.chmod(file, 0o600)
