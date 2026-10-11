import os
import unittest
from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from smartlock_protocol.distribution_lab import Recipient, kdc_pair, public_packet, run


class DistributionLabTests(unittest.TestCase):
    def test_kdc_binds_identity_session_expiration_and_replay(self):
        keys = {name: os.urandom(32) for name in ('alice', 'bob')}
        session, (ticket, other) = kdc_pair(keys, 'alice', 'bob', clock=lambda: 1000)
        a, b = Recipient('alice', lambda: 1000), Recipient('bob', lambda: 1000)
        with self.assertRaises(InvalidTag):
            a.receive_kdc(ticket, os.urandom(32), 'bob', session)
        with self.assertRaises(InvalidTag):
            a.receive_kdc(ticket[:-1] + bytes([ticket[-1] ^ 1]), keys['alice'], 'bob', session)
        with self.assertRaises(ValueError):
            a.receive_kdc(ticket, keys['alice'], 'mallory', session)
        with self.assertRaises(ValueError):
            a.receive_kdc(ticket, keys['alice'], 'bob', '0' * 32)
        with self.assertRaises(ValueError):
            Recipient('alice', lambda: 1030).receive_kdc(ticket, keys['alice'], 'bob', session)
        self.assertEqual(a.receive_kdc(ticket, keys['alice'], 'bob', session),
                         b.receive_kdc(other, keys['bob'], 'alice', session))
        with self.assertRaises(ValueError):
            a.receive_kdc(ticket, keys['alice'], 'bob', session)

    def test_signed_public_distribution_rejects_impersonation_and_replay(self):
        issuer, fake = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        session, key = os.urandom(16).hex(), os.urandom(32)
        packet = public_packet('alice', 'bob', private.public_key(), issuer, session, key, clock=lambda: 1000)
        receiver = Recipient('bob', lambda: 1000)
        with self.assertRaises(InvalidSignature):
            receiver.receive_public(packet, private, fake.public_key(), 'alice', session)
        modified = (dict(packet[0], sender='mallory'), packet[1], packet[2])
        with self.assertRaises(InvalidSignature):
            receiver.receive_public(modified, private, issuer.public_key(), 'mallory', session)
        with self.assertRaises(ValueError):
            Recipient('bob', lambda: 1030).receive_public(packet, private, issuer.public_key(), 'alice', session)
        self.assertEqual(receiver.receive_public(packet, private, issuer.public_key(), 'alice', session), key)
        with self.assertRaises(ValueError):
            receiver.receive_public(packet, private, issuer.public_key(), 'alice', session)

    def test_issuance_requires_registered_distinct_identities(self):
        keys = {'alice': os.urandom(32)}
        with self.assertRaises(ValueError):
            kdc_pair(keys, 'alice', 'unknown')
        with self.assertRaises(ValueError):
            kdc_pair(keys, 'alice', 'alice')
        with self.assertRaises(ValueError):
            kdc_pair(dict(keys, bob=keys['alice']), 'alice', 'bob')
        with self.assertRaises(ValueError):
            kdc_pair(dict(keys, bob=os.urandom(16)), 'alice', 'bob')

    def test_report_passes_without_claiming_forward_secrecy(self):
        report = run()
        self.assertTrue(report['passed'])
        self.assertFalse(report['kdc']['forward_secrecy'])
        self.assertFalse(report['public_distribution']['forward_secrecy'])
