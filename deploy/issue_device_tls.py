"""Issue a distinct device-service certificate using the existing local laboratory CA."""
import argparse
from datetime import datetime, timedelta, timezone
import ipaddress
import os
from pathlib import Path
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True, help='Pi address or DNS name reached by the backend')
    args = parser.parse_args()
    directory = ROOT / 'deploy/tls'
    if any((directory / name).exists() for name in ('device.crt', 'device.key')):
        raise SystemExit('Existing device certificate found; refusing to overwrite it.')
    ca = x509.load_pem_x509_certificate((directory/'ca.crt').read_bytes())
    ca_key = serialization.load_pem_private_key((directory/'ca.key').read_bytes(), password=None)
    if ca_key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo) != ca.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo):
        raise SystemExit('CA certificate/key mismatch')
    try:
        host = x509.IPAddress(ipaddress.ip_address(args.host))
    except ValueError:
        host = x509.DNSName(args.host)
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, args.host)]))
            .issuer_name(ca.subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now-timedelta(minutes=5)).not_valid_after(min(now+timedelta(days=90), ca.not_valid_after_utc))
            .add_extension(x509.SubjectAlternativeName([host]), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(ca_key, hashes.SHA256()))
    files = {'device.crt': cert.public_bytes(serialization.Encoding.PEM),
             'device.key': key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())}
    for name, content in files.items():
        with (directory/name).open('xb') as file:
            file.write(content)
        os.chmod(directory/name, 0o444)
    print('Device certificate issued. Transfer only device.crt, device.key and ca.crt to the Pi.')


if __name__ == '__main__':
    main()
