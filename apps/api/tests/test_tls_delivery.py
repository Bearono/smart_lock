"""Verify certificate identities and refusal to replace installed TLS material."""

import importlib.util
import ipaddress
import os
import ssl
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

ROOT = Path(__file__).resolve().parents[3]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "deploy" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def memory_handshake(ca, cert, key, hostname, *, strict=True):
    """Real OpenSSL verification without binding a TCP port."""
    client_context = ssl.create_default_context(cafile=str(ca))
    if strict:
        client_context.verify_flags |= ssl.VERIFY_X509_STRICT
    else:
        # Compatibility check for clients retaining the pre-repair trust anchor.
        client_context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(str(cert), str(key))
    client_in, client_out, server_in, server_out = (ssl.MemoryBIO() for _ in range(4))
    client = client_context.wrap_bio(client_in, client_out, server_hostname=hostname)
    server = server_context.wrap_bio(server_in, server_out, server_side=True)
    client_done = server_done = False
    for _ in range(50):
        for connection, done in ((client, client_done), (server, server_done)):
            if done:
                continue
            try:
                connection.do_handshake()
                if connection is client:
                    client_done = True
                else:
                    server_done = True
            except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
                pass
        for incoming, outgoing in ((server_in, client_out), (client_in, server_out)):
            pending = outgoing.read()
            if pending:
                incoming.write(pending)
        if client_done and server_done:
            return
    raise AssertionError("TLS handshake did not complete")


class TLSDeliveryTests(unittest.TestCase):
    def test_distinct_device_identity_signed_by_ca_and_no_overwrite(self):
        initial, issuer = load("init_local_tls"), load("issue_device_tls")
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "deploy/tls"
            try:
                with patch.object(initial, "ROOT", root), patch("sys.argv", ["init_local_tls"]):
                    initial.main()
                with (
                    patch.object(issuer, "ROOT", root),
                    patch("sys.argv", ["issue_device_tls", "--host", "192.168.1.20"]),
                ):
                    issuer.main()
                    saved = (directory / "device.key").read_bytes()
                    with self.assertRaises(SystemExit):
                        issuer.main()
                    self.assertEqual(saved, (directory / "device.key").read_bytes())
                ca = x509.load_pem_x509_certificate((directory / "ca.crt").read_bytes())
                device = x509.load_pem_x509_certificate((directory / "device.crt").read_bytes())
                server = x509.load_pem_x509_certificate((directory / "server.crt").read_bytes())
                device.verify_directly_issued_by(ca)
                san = device.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
                self.assertEqual(
                    san.get_values_for_type(x509.IPAddress), [ipaddress.ip_address("192.168.1.20")]
                )
                encoding, form = (
                    serialization.Encoding.DER,
                    serialization.PublicFormat.SubjectPublicKeyInfo,
                )
                self.assertNotEqual(
                    device.public_key().public_bytes(encoding, form),
                    server.public_key().public_bytes(encoding, form),
                )
                self.assertLessEqual(device.not_valid_after_utc, ca.not_valid_after_utc)
                memory_handshake(
                    directory / "ca.crt",
                    directory / "device.crt",
                    directory / "device.key",
                    "192.168.1.20",
                )
                memory_handshake(
                    directory / "ca.crt",
                    directory / "server.crt",
                    directory / "server.key",
                    "localhost",
                )
                with self.assertRaises(ssl.SSLCertVerificationError):
                    memory_handshake(
                        directory / "ca.crt",
                        directory / "server.crt",
                        directory / "server.key",
                        "wrong.example",
                    )
            finally:
                # Windows also treats chmod's read-only flag as a deletion restriction.
                for file in directory.glob("*"):
                    os.chmod(file, 0o600)

    def test_repair_restores_strict_validation_without_changing_keys_names_or_expiry(self):
        initial, repair = load("init_local_tls"), load("repair_local_tls")
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(initial, "ROOT", root), patch("sys.argv", ["init_local_tls"]):
                initial.main()
            directory = root / "deploy/tls"
            try:
                key = serialization.load_pem_private_key(
                    (directory / "ca.key").read_bytes(), password=None
                )
                for name in ("ca.crt", "server.crt"):
                    path = directory / name
                    cert = x509.load_pem_x509_certificate(path.read_bytes())
                    legacy = (
                        x509.CertificateBuilder()
                        .subject_name(cert.subject)
                        .issuer_name(cert.issuer)
                        .public_key(cert.public_key())
                        .serial_number(cert.serial_number)
                        .not_valid_before(cert.not_valid_before_utc)
                        .not_valid_after(cert.not_valid_after_utc)
                    )
                    for extension in cert.extensions:
                        if not isinstance(
                            extension.value,
                            (x509.SubjectKeyIdentifier, x509.AuthorityKeyIdentifier),
                        ):
                            legacy = legacy.add_extension(extension.value, extension.critical)
                    os.chmod(path, 0o600)
                    path.write_bytes(
                        legacy.sign(key, hashes.SHA256()).public_bytes(serialization.Encoding.PEM)
                    )
                before = {path.name: path.read_bytes() for path in directory.iterdir()}
                with self.assertRaises(ssl.SSLCertVerificationError):
                    memory_handshake(
                        directory / "ca.crt",
                        directory / "server.crt",
                        directory / "server.key",
                        "localhost",
                    )
                output = root / "fixed"
                repair.stage(
                    directory / "ca.crt", directory / "ca.key", [directory / "server.crt"], output
                )
                memory_handshake(
                    output / "ca.crt", output / "server.crt", directory / "server.key", "localhost"
                )
                memory_handshake(
                    directory / "ca.crt",
                    output / "server.crt",
                    directory / "server.key",
                    "localhost",
                    strict=False,
                )
                self.assertEqual(
                    before, {path.name: path.read_bytes() for path in directory.iterdir()}
                )
                self.assertEqual(list(output.glob("*.key")), [])
                for name in ("ca.crt", "server.crt"):
                    old = x509.load_pem_x509_certificate(before[name])
                    new = x509.load_pem_x509_certificate((output / name).read_bytes())
                    self.assertEqual(old.subject, new.subject)
                    self.assertEqual(old.issuer, new.issuer)
                    self.assertEqual(old.not_valid_after_utc, new.not_valid_after_utc)
                    self.assertEqual(
                        repair.public_key_bytes(old.public_key()),
                        repair.public_key_bytes(new.public_key()),
                    )
                with self.assertRaises(FileExistsError):
                    repair.stage(
                        directory / "ca.crt",
                        directory / "ca.key",
                        [directory / "server.crt"],
                        output,
                    )
            finally:
                for path in directory.glob("*"):
                    os.chmod(path, 0o600)
