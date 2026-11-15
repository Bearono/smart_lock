"""Independent course D2D exchange with pinned public keys and durable replay state.

This channel never imports the production lock, changes authorization or executes messages.
Private/session keys are authenticated-encrypted at rest under a separate local master key.
"""
import base64
from contextlib import closing
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import time

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VERSION = 'SL-AUDIO-D2D-1'
TTL = 300
BINDING_FIELDS = frozenset(('version', 'sender', 'recipient', 'session', 'challenge', 'expires'))
SIGN_CONTEXT = b'smartlock/audio-d2d/v1\0'
CONFIRM_CONTEXT = b'smartlock/audio-confirm/v1\0'
MESSAGE_CONTEXT = b'smartlock/audio-message/v1\0'
STORE_CONTEXT = b'smartlock/audio-local-store/v1\0'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('utf-8')


def b64e(value):
    return base64.b64encode(value).decode('ascii')


def b64d(value):
    if not isinstance(value, str) or len(value) > 16384:
        raise ValueError('Invalid base64 field')
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError('Invalid base64 field') from exc
    if b64e(decoded) != value:
        raise ValueError('Noncanonical base64 field')
    return decoded


def identity(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,50}', value):
        raise ValueError('Identity must contain 1..50 ASCII letters, numbers, underscores or hyphens')
    return value


def validate_binding(binding, now):
    if not isinstance(binding, dict) or set(binding) != BINDING_FIELDS or binding.get('version') != VERSION:
        raise ValueError('Invalid D2D binding')
    if identity(binding['sender']) == identity(binding['recipient']):
        raise ValueError('Sender and recipient must differ')
    for name in ('session', 'challenge'):
        if not isinstance(binding[name], str) or not re.fullmatch(r'[0-9a-f]{32}', binding[name]):
            raise ValueError('Invalid D2D session or challenge')
    if type(binding['expires']) is not int or not now < binding['expires'] <= now + TTL:
        raise ValueError('Expired or overlong D2D binding')
    return binding


def oaep():
    return padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(),
                        label=b'smart-lock/course/key-wrap/v1')


def public_der(key):
    return key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


def load_public(encoded, kind):
    try:
        key = serialization.load_der_public_key(encoded)
    except (ValueError, TypeError) as exc:
        raise ValueError('Invalid pinned public key') from exc
    if kind == 'rsa':
        if not isinstance(key, rsa.RSAPublicKey) or key.key_size != 2048 or key.public_numbers().e != 65537:
            raise ValueError('Recipient must use RSA-2048 with exponent 65537')
    elif kind == 'ec':
        if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
            raise ValueError('Issuer must use ECDSA P-256')
    else:
        raise ValueError('Unsupported public key type')
    if public_der(key) != encoded:
        raise ValueError('Public key must use canonical DER SubjectPublicKeyInfo')
    return key


def strict_object(value, fields):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError('Invalid packet fields')


class Peer:
    """One local identity. SQLite transactions arbitrate both acceptance and message replay."""
    def __init__(self, directory, *, create=False, clock=time.time):
        self.directory = Path(directory)
        self.clock = clock
        self.master_path = self.directory / 'master.key'
        self.database = self.directory / 'state.sqlite3'
        if self.directory.is_symlink():
            raise ValueError('State directory must not be a symbolic link')
        if create:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            if self.master_path.exists() or self.database.exists():
                raise FileExistsError('D2D state already exists')
            os.chmod(self.directory, 0o700)
            descriptor = os.open(self.master_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'wb') as handle:
                handle.write(os.urandom(32))
        for path in (self.master_path, self.database):
            if path.is_symlink():
                raise ValueError('State files must not be symbolic links')
            if path.exists() and os.name != 'nt' and stat.S_IMODE(path.stat().st_mode) & 0o077:
                raise ValueError('State files require mode 0600')
        if not create and not self.database.is_file():
            raise ValueError('Initialize the local peer first')
        self.master = self.master_path.read_bytes()
        if len(self.master) != 32:
            raise ValueError('Invalid local master key')
        with self.connect() as connection:
            if create:
                connection.executescript('''
                    CREATE TABLE metadata(name TEXT PRIMARY KEY, value BLOB NOT NULL);
                    CREATE TABLE pending(session TEXT PRIMARY KEY, binding TEXT NOT NULL, consumed INTEGER NOT NULL DEFAULT 0);
                    CREATE TABLE sessions(session TEXT PRIMARY KEY, binding TEXT NOT NULL, secret BLOB NOT NULL,
                                          role TEXT NOT NULL, confirmed INTEGER NOT NULL DEFAULT 0);
                    CREATE TABLE message_receipts(session TEXT NOT NULL, nonce TEXT NOT NULL,
                                                  PRIMARY KEY(session, nonce));
                ''')
        os.chmod(self.database, 0o600)

    def connect(self):
        return closing(sqlite3.connect(self.database, timeout=5, isolation_level=None))

    def encrypt_local(self, label, content):
        nonce = os.urandom(12)
        return nonce + AESGCM(self.master).encrypt(nonce, content, STORE_CONTEXT + label.encode('ascii'))

    def decrypt_local(self, label, content):
        try:
            return AESGCM(self.master).decrypt(content[:12], content[12:], STORE_CONTEXT + label.encode('ascii'))
        except (ValueError, InvalidTag) as exc:
            raise ValueError('Local state authentication failed') from exc

    def initialize(self, role, name):
        identity(name)
        if role == 'issuer':
            private = ec.generate_private_key(ec.SECP256R1())
        elif role == 'receiver':
            private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        else:
            raise ValueError('Unsupported peer role')
        encoded = private.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
                                         serialization.NoEncryption())
        with self.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            try:
                for key, value in (('role', role.encode()), ('identity', name.encode()), ('private', encoded)):
                    connection.execute('INSERT INTO metadata VALUES (?, ?)', (key, self.encrypt_local(key, value)))
                connection.execute('COMMIT')
            except Exception:
                connection.execute('ROLLBACK')
                raise
        return public_der(private.public_key())

    def local_value(self, name):
        with self.connect() as connection:
            row = connection.execute('SELECT value FROM metadata WHERE name=?', (name,)).fetchone()
        if row is None:
            raise ValueError('Local peer is not initialized')
        return self.decrypt_local(name, row[0])

    def require_role(self, role):
        if self.local_value('role').decode() != role:
            raise ValueError('Operation is not available for this peer role')
        return self.local_value('identity').decode()

    def public_key(self):
        private = serialization.load_der_private_key(self.local_value('private'), password=None)
        return public_der(private.public_key())

    def create_request(self, sender, ttl=TTL):
        recipient = self.require_role('receiver')
        if type(ttl) is not int or not 1 <= ttl <= TTL:
            raise ValueError('TTL must be between 1 and 300 seconds')
        binding = dict(version=VERSION, sender=identity(sender), recipient=recipient,
                       session=os.urandom(16).hex(), challenge=os.urandom(16).hex(),
                       expires=int(self.clock()) + ttl)
        validate_binding(binding, self.clock())
        with self.connect() as connection:
            connection.execute('INSERT INTO pending(session,binding) VALUES (?,?)',
                               (binding['session'], canonical(binding).decode()))
        return dict(binding, recipient_public_key=b64e(self.public_key()))

    def issue(self, request, pinned_receiver_public):
        sender = self.require_role('issuer')
        strict_object(request, BINDING_FIELDS | {'recipient_public_key'})
        binding = validate_binding({name: request[name] for name in BINDING_FIELDS}, self.clock())
        if binding['sender'] != sender:
            raise ValueError('Request names another issuer')
        recipient_key = load_public(pinned_receiver_public, 'rsa')
        if not hmac.compare_digest(b64d(request['recipient_public_key']), pinned_receiver_public):
            raise ValueError('Request public key does not match locally pinned recipient key')
        key = os.urandom(32)
        wrapped = recipient_key.encrypt(key, oaep())
        private = serialization.load_der_private_key(self.local_value('private'), password=None)
        signature = private.sign(SIGN_CONTEXT + canonical(binding) + wrapped, ec.ECDSA(hashes.SHA256()))
        with self.connect() as connection:
            try:
                connection.execute('INSERT INTO sessions(session,binding,secret,role) VALUES (?,?,?,?)',
                                   (binding['session'], canonical(binding).decode(),
                                    self.encrypt_local('session/' + binding['session'], key), 'issuer'))
            except sqlite3.IntegrityError as exc:
                raise ValueError('Session has already been issued') from exc
        return {'binding': binding, 'wrapped': b64e(wrapped), 'signature': b64e(signature)}

    def accept(self, packet, pinned_issuer_public):
        recipient = self.require_role('receiver')
        strict_object(packet, ('binding', 'wrapped', 'signature'))
        binding = validate_binding(packet['binding'], self.clock())
        if binding['recipient'] != recipient:
            raise ValueError('Packet names another recipient')
        wrapped, signature = b64d(packet['wrapped']), b64d(packet['signature'])
        if len(wrapped) != 256:
            raise ValueError('Invalid wrapped key length')
        issuer = load_public(pinned_issuer_public, 'ec')
        try:
            issuer.verify(signature, SIGN_CONTEXT + canonical(binding) + wrapped, ec.ECDSA(hashes.SHA256()))
        except InvalidSignature as exc:
            raise ValueError('Pinned issuer signature verification failed') from exc
        with self.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            try:
                row = connection.execute('SELECT binding,consumed FROM pending WHERE session=?',
                                         (binding['session'],)).fetchone()
                if row is None or row[0] != canonical(binding).decode() or row[1]:
                    raise ValueError('No matching unused pending challenge')
                private = serialization.load_der_private_key(self.local_value('private'), password=None)
                key = private.decrypt(wrapped, oaep())
                if len(key) != 32:
                    raise ValueError('Invalid distributed key')
                connection.execute('INSERT INTO sessions(session,binding,secret,role,confirmed) VALUES (?,?,?,?,1)',
                                   (binding['session'], canonical(binding).decode(),
                                    self.encrypt_local('session/' + binding['session'], key), 'receiver'))
                connection.execute('UPDATE pending SET consumed=1 WHERE session=?', (binding['session'],))
                connection.execute('COMMIT')
            except Exception:
                connection.execute('ROLLBACK')
                raise
        return self.confirmation(binding['session'])

    def session(self, connection, session_id, role):
        if not isinstance(session_id, str) or not re.fullmatch(r'[0-9a-f]{32}', session_id):
            raise ValueError('Invalid session ID')
        row = connection.execute('SELECT binding,secret,role,confirmed FROM sessions WHERE session=?',
                                 (session_id,)).fetchone()
        if row is None or row[2] != role:
            raise ValueError('Unknown session for this peer role')
        binding = validate_binding(json.loads(row[0]), self.clock())
        return binding, self.decrypt_local('session/' + session_id, row[1]), bool(row[3])

    def confirmation(self, session_id):
        self.require_role('receiver')
        with self.connect() as connection:
            binding, key, _ = self.session(connection, session_id, 'receiver')
        return {'binding': binding, 'type': 'confirm',
                'proof': b64e(hmac.new(key, CONFIRM_CONTEXT + canonical(binding), hashlib.sha256).digest())}

    def verify_confirmation(self, packet):
        self.require_role('issuer')
        strict_object(packet, ('binding', 'type', 'proof'))
        binding = validate_binding(packet['binding'], self.clock())
        if packet['type'] != 'confirm':
            raise ValueError('Invalid confirmation type')
        with self.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            try:
                stored, key, confirmed = self.session(connection, binding['session'], 'issuer')
                expected = hmac.new(key, CONFIRM_CONTEXT + canonical(stored), hashlib.sha256).digest()
                if binding != stored or not hmac.compare_digest(b64d(packet['proof']), expected):
                    raise ValueError('Invalid key confirmation')
                if confirmed:
                    raise ValueError('Confirmation already consumed')
                connection.execute('UPDATE sessions SET confirmed=1 WHERE session=?', (binding['session'],))
                connection.execute('COMMIT')
            except Exception:
                connection.execute('ROLLBACK')
                raise
        return {'binding': binding, 'type': 'confirmed', 'confirmed': True}

    def seal(self, session_id, plaintext):
        self.require_role('receiver')
        if not isinstance(plaintext, bytes) or not 1 <= len(plaintext) <= 1024:
            raise ValueError('Message must contain 1..1024 bytes')
        with self.connect() as connection:
            binding, key, _ = self.session(connection, session_id, 'receiver')
        nonce = os.urandom(12)
        return {'binding': binding, 'type': 'message', 'nonce': b64e(nonce),
                'ciphertext': b64e(AESGCM(key).encrypt(nonce, plaintext, MESSAGE_CONTEXT + canonical(binding)))}

    def open_message(self, packet):
        self.require_role('issuer')
        strict_object(packet, ('binding', 'type', 'nonce', 'ciphertext'))
        binding = validate_binding(packet['binding'], self.clock())
        nonce, ciphertext = b64d(packet['nonce']), b64d(packet['ciphertext'])
        if packet['type'] != 'message' or len(nonce) != 12 or not 17 <= len(ciphertext) <= 1040:
            raise ValueError('Invalid encrypted message')
        with self.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            try:
                stored, key, confirmed = self.session(connection, binding['session'], 'issuer')
                if binding != stored or not confirmed:
                    raise ValueError('Session is unconfirmed or binding does not match')
                plaintext = AESGCM(key).decrypt(nonce, ciphertext, MESSAGE_CONTEXT + canonical(binding))
                connection.execute('INSERT INTO message_receipts VALUES (?,?)',
                                   (binding['session'], packet['nonce']))
                connection.execute('COMMIT')
            except sqlite3.IntegrityError as exc:
                connection.execute('ROLLBACK')
                raise ValueError('Message nonce already consumed') from exc
            except InvalidTag as exc:
                connection.execute('ROLLBACK')
                raise ValueError('Message authentication failed') from exc
            except Exception:
                connection.execute('ROLLBACK')
                raise
        return plaintext
