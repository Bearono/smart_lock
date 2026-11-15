"""Authenticated credential storage; plaintext is accepted only during offline migration."""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app
from sqlalchemy.types import Text, TypeDecorator

PREFIX = 'enc:v1:'


class CredentialStorageError(RuntimeError):
    pass


def cipher():
    # Independent purpose from device-session storage and JWT signing.
    root = current_app.config['SECRET_KEY']
    root = root.encode() if isinstance(root, str) else root
    key = hashlib.sha256(b'smart-lock-mfa-storage-v1\0' + root).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(value):
    return PREFIX + cipher().encrypt(value.encode('utf-8')).decode('ascii')


def decrypt(value, *, allow_legacy=False):
    if not value.startswith(PREFIX):
        if allow_legacy or current_app.config['DEPLOYMENT_ENV'] != 'production':
            return value
        raise CredentialStorageError('Credential migration required')
    try:
        return cipher().decrypt(value[len(PREFIX):].encode('ascii')).decode('utf-8')
    except (InvalidToken, UnicodeError, ValueError) as exc:
        raise CredentialStorageError('Credential storage authentication failed') from exc


class EncryptedCredential(TypeDecorator):
    """Keep the domain API unchanged while never writing plaintext credentials."""
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else encrypt(value)

    def process_result_value(self, value, dialect):
        return None if value is None else decrypt(value)


def migrate_credentials():
    from sqlalchemy import text
    from app import db
    rows = db.session.execute(text('SELECT id, credential_data FROM mfa_credentials')).all()
    for identity, value in rows:
        if value.startswith(PREFIX):
            decrypt(value)  # Wrong keys or corrupt ciphertext must stop the upgrade.
        else:
            db.session.execute(text('UPDATE mfa_credentials SET credential_data=:value WHERE id=:id'),
                               {'value': encrypt(value), 'id': identity})
