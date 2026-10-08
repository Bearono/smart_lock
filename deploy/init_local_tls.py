"""Create a local laboratory CA and certificate. Never replace existing keys.

For public deployments supply certificates from your normal trusted certificate
provider. This utility is for a controlled LAN/course demonstration only.
"""
import argparse
from datetime import datetime, timedelta, timezone
import ipaddress
import os
from pathlib import Path
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', action='append', default=['localhost', '127.0.0.1'])
    args = parser.parse_args()
    destination = ROOT / 'deploy/tls'
    destination.mkdir(parents=True, exist_ok=True)
    names = ['ca.crt', 'ca.key', 'server.crt', 'server.key']
    if any((destination / name).exists() for name in names):
        raise SystemExit('Existing TLS material found; refusing to overwrite it.')
    san = []
    for host in dict.fromkeys(args.host):
        try:
            san.append(x509.IPAddress(ipaddress.ip_address(host)))
        except ValueError:
            san.append(x509.DNSName(host))
    now = datetime.now(timezone.utc)
    ca_key, server_key = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'SmartLock course local CA')])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
          .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=365))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
          .sign(ca_key, hashes.SHA256()))
    cert = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, args.host[0])]))
            .issuer_name(ca_name).public_key(server_key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=90))
            .add_extension(x509.SubjectAlternativeName(san), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(ca_key, hashes.SHA256()))
    contents = {
        'ca.crt': ca.public_bytes(serialization.Encoding.PEM),
        'server.crt': cert.public_bytes(serialization.Encoding.PEM),
        'ca.key': ca_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()),
        'server.key': server_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()),
    }
    os.chmod(destination, 0o700)
    for name, content in contents.items():
        with (destination / name).open('xb') as file:
            file.write(content)
        os.chmod(destination / name, 0o444)
    print('Local TLS material created. Distribute only ca.crt to clients; protect both private keys.')


if __name__ == '__main__':
    main()
