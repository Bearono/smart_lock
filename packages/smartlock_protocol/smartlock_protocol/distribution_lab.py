"""In-memory course key distribution, isolated from production device transport.

An operator authorizes issuance. Long-term keys / pinned issuer public keys are
provisioned out of band. No enrollment, network API or durable replay store is
provided; this module must not be substituted for the deployed protocol.
"""
import argparse
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from smartlock_protocol.course_lab import oaep


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def identity(value):
    if not isinstance(value, str) or not value or len(value) > 50 or not value.isascii() or not all(
            c.isalnum() or c in '_-' for c in value):
        raise ValueError('Invalid lab identity')
    return value


def grant(sender, recipient, session, expires):
    identity(sender)
    identity(recipient)
    if sender == recipient or not isinstance(session, str) or len(session) != 32 or any(
            c not in '0123456789abcdef' for c in session):
        raise ValueError('Invalid session binding')
    if type(expires) is not int:
        raise ValueError('Invalid expiration')
    return {'sender': sender, 'recipient': recipient, 'session': session, 'expires': expires}


class Recipient:
    """Lab-only recipient. Replay state is volatile and capped, never silently evicted."""
    def __init__(self, name, clock=time.time):
        self.name = identity(name)
        self.clock = clock
        self.seen = set()

    def accept(self, header, key, peer, session):
        expected = grant(peer, self.name, session, header.get('expires'))
        now = self.clock()
        if header != expected or not now < header['expires'] <= now + 60:
            raise ValueError('Wrong recipient, peer, session or expiration')
        if not isinstance(key, bytes) or len(key) != 32:
            raise ValueError('Invalid distributed key')
        if session in self.seen or len(self.seen) >= 2048:
            raise ValueError('Replay or exhausted lab replay capacity')
        self.seen.add(session)
        return key

    def receive_kdc(self, ticket, long_term_key, peer, session):
        plain = AESGCM(long_term_key).decrypt(ticket[:12], ticket[12:], b'course/kdc/v1/' + self.name.encode())
        payload = json.loads(plain)
        key = base64.b64decode(payload.pop('key'), validate=True)
        return self.accept(payload, key, peer, session)

    def receive_public(self, packet, private_key, issuer_public_key, peer, session):
        header, ciphertext, signature = packet
        # Verify the pinned issuer before decrypting or consuming replay state.
        issuer_public_key.verify(signature, b'course/rsa-distribution/v1\0' + canonical(header) + ciphertext,
                                 ec.ECDSA(hashes.SHA256()))
        return self.accept(header, private_key.decrypt(ciphertext, oaep()), peer, session)


def kdc_pair(registered_keys, alice, bob, clock=time.time):
    """Operator-authorized KDC issuance; KDC knows the distributed session key."""
    if alice not in registered_keys or bob not in registered_keys:
        raise ValueError('Unregistered recipient')
    if any(not isinstance(registered_keys[name], bytes) or len(registered_keys[name]) != 32
           for name in (alice, bob)):
        raise ValueError('KDC recipients require distinct provisioned AES-256 keys')
    if registered_keys[alice] == registered_keys[bob]:
        raise ValueError('KDC recipients must not share a long-term identity key')
    session, key, expires = os.urandom(16).hex(), os.urandom(32), int(clock()) + 30
    tickets = []
    for peer, recipient in ((bob, alice), (alice, bob)):
        header = grant(peer, recipient, session, expires)
        payload = dict(header, key=base64.b64encode(key).decode())
        nonce = os.urandom(12)
        tickets.append(nonce + AESGCM(registered_keys[recipient]).encrypt(
            nonce, canonical(payload), b'course/kdc/v1/' + recipient.encode()))
    return session, tuple(tickets)


def public_packet(sender, recipient, recipient_public_key, issuer_private_key, session, key, clock=time.time):
    header = grant(sender, recipient, session, int(clock()) + 30)
    if not isinstance(key, bytes) or len(key) != 32:
        raise ValueError('Invalid distributed key')
    ciphertext = recipient_public_key.encrypt(key, oaep())
    signature = issuer_private_key.sign(b'course/rsa-distribution/v1\0' + canonical(header) + ciphertext,
                                        ec.ECDSA(hashes.SHA256()))
    return header, ciphertext, signature


def run():
    keys = {name: os.urandom(32) for name in ('alice', 'bob')}
    session, (a_ticket, b_ticket) = kdc_pair(keys, 'alice', 'bob')
    alice, bob = Recipient('alice'), Recipient('bob')
    a_key = alice.receive_kdc(a_ticket, keys['alice'], 'bob', session)
    b_key = bob.receive_kdc(b_ticket, keys['bob'], 'alice', session)
    rejected = False
    try:
        alice.receive_kdc(a_ticket, keys['alice'], 'bob', session)
    except ValueError:
        rejected = True
    issuer = ec.generate_private_key(ec.SECP256R1())
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    session, secret = os.urandom(16).hex(), os.urandom(32)
    packet = public_packet('alice', 'bob', private.public_key(), issuer, session, secret)
    received = bob.receive_public(packet, private, issuer.public_key(), 'alice', session)
    modified = (dict(packet[0], recipient='mallory'), packet[1], packet[2])
    tamper_rejected = False
    try:
        Recipient('mallory').receive_public(modified, private, issuer.public_key(), 'alice', session)
    except InvalidSignature:
        tamper_rejected = True
    result = {'created_at': datetime.now(timezone.utc).isoformat(),
              'scope': 'operator-authorized in-memory lab; no network or durable replay claims',
              'kdc': {'shared_key_agrees': a_key == b_key, 'replay_rejected': rejected,
                      'issuer_knows_session_key': True, 'forward_secrecy': False},
              'public_distribution': {'received_key_matches': received == secret,
                                      'signed_binding_tamper_rejected': tamper_rejected,
                                      'forward_secrecy': False}}
    result['passed'] = a_key == b_key and rejected and received == secret and tamper_rejected
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
