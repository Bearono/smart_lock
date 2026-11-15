"""Stage standards-compliant public certificates using the existing laboratory keys.

Inputs and private keys are never replaced. Review/test the output before installing
it. Subject names, SANs, public keys and expiry dates remain unchanged.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa


def public_key_bytes(key):
    return key.public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def corrected_certificate(cert, ca_key, ca_public_key):
    builder = (
        x509.CertificateBuilder()
        .subject_name(cert.subject)
        .issuer_name(cert.issuer)
        .public_key(cert.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(cert.not_valid_before_utc)
        .not_valid_after(cert.not_valid_after_utc)
    )
    for extension in cert.extensions:
        if isinstance(extension.value, (x509.SubjectKeyIdentifier, x509.AuthorityKeyIdentifier)):
            continue
        builder = builder.add_extension(extension.value, critical=extension.critical)
    builder = builder.add_extension(
        x509.SubjectKeyIdentifier.from_public_key(cert.public_key()), critical=False
    ).add_extension(
        x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_public_key), critical=False
    )
    try:
        cert.extensions.get_extension_for_class(x509.KeyUsage)
    except x509.ExtensionNotFound:
        is_ca = cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
        builder = builder.add_extension(
            x509.KeyUsage(not is_ca, False, False, False, False, is_ca, is_ca, False, False),
            critical=True,
        )
    return builder.sign(ca_key, hashes.SHA256())


def stage(ca_cert, ca_key_file, certificates, output):
    ca_cert, ca_key_file, output = Path(ca_cert), Path(ca_key_file), Path(output)
    ca = x509.load_pem_x509_certificate(ca_cert.read_bytes())
    key = serialization.load_pem_private_key(ca_key_file.read_bytes(), password=None)
    if not isinstance(key, (ec.EllipticCurvePrivateKey, rsa.RSAPrivateKey)) or public_key_bytes(
        key.public_key()
    ) != public_key_bytes(ca.public_key()):
        raise ValueError("CA certificate/key mismatch or unsupported key type")
    ca.verify_directly_issued_by(ca)
    if not ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
        raise ValueError("Expected the self-signed laboratory CA")
    inputs = {"ca.crt": ca}
    for path in map(Path, certificates):
        if path.name.casefold() in {name.casefold() for name in inputs} or path.suffix != ".crt":
            raise ValueError("Certificate output names must be distinct .crt filenames")
        cert = x509.load_pem_x509_certificate(path.read_bytes())
        cert.verify_directly_issued_by(ca)
        if cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
            raise ValueError("Only server/device leaf certificates are supported")
        if cert.not_valid_after_utc > ca.not_valid_after_utc:
            raise ValueError("Leaf certificate must not outlive its CA")
        inputs[path.name] = cert
    now = datetime.now(timezone.utc)
    if any(
        not cert.not_valid_before_utc <= now < cert.not_valid_after_utc for cert in inputs.values()
    ):
        raise ValueError("Certificate is not currently valid; perform a separate renewal")
    fixed = {
        name: corrected_certificate(cert, key, ca.public_key()) for name, cert in inputs.items()
    }
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    report = {
        "private_keys_changed": False,
        "identities_preserved": True,
        "expiry_extended": False,
        "files": {},
    }
    for name, cert in fixed.items():
        content = cert.public_bytes(serialization.Encoding.PEM)
        with (output / name).open("xb") as handle:
            handle.write(content)
        report["files"][name] = {
            "sha256": hashlib.sha256(content).hexdigest(),
            "public_key_sha256": hashlib.sha256(public_key_bytes(cert.public_key())).hexdigest(),
        }
    (output / "manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ca-cert", type=Path, required=True)
    parser.add_argument("--ca-key", type=Path, required=True)
    parser.add_argument("--certificate", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        stage(args.ca_cert, args.ca_key, args.certificate, args.output)
    except (ValueError, OSError, x509.ExtensionNotFound) as exc:
        parser.exit(2, f"Certificate staging failed: {exc}\n")
    print(
        "Public certificates staged; original files, private keys, names and expiry dates are unchanged."
    )


if __name__ == "__main__":
    main()
