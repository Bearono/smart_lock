"""Versioned authenticated media files, bound to their asset and device identity."""
import hashlib
import os
from pathlib import Path
import tempfile

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from flask import current_app

from app.credential_storage import CredentialStorageError

MAGIC = b'SLMEDIA1\0'


def _key():
    root = current_app.config['SECRET_KEY']
    root = root.encode() if isinstance(root, str) else root
    return hashlib.sha256(b'smart-lock-private-media-v1\0' + root).digest()


def protect(content, filename, device_id):
    nonce = os.urandom(12)
    aad = f'SLMEDIA1\0{filename}\0{device_id}'.encode()
    return MAGIC + nonce + AESGCM(_key()).encrypt(nonce, content, aad)


def unprotect(content, filename, device_id):
    if not content.startswith(MAGIC):
        if current_app.config['DEPLOYMENT_ENV'] != 'production':
            return content
        raise CredentialStorageError('Media migration required')
    nonce = content[len(MAGIC):len(MAGIC) + 12]
    aad = f'SLMEDIA1\0{filename}\0{device_id}'.encode()
    try:
        return AESGCM(_key()).decrypt(nonce, content[len(MAGIC) + 12:], aad)
    except (InvalidTag, ValueError) as exc:
        raise CredentialStorageError('Media storage authentication failed') from exc


def migrate_media():
    from app.models import MediaAsset
    root = Path(current_app.config['UPLOAD_FOLDER']).resolve()
    for asset in MediaAsset.query.yield_per(100):
        path = root / asset.filename
        if path.is_symlink() or path.resolve().parent != root:
            raise ValueError('Invalid media path during migration')
        if not path.is_file():
            continue
        content = path.read_bytes()
        if content.startswith(MAGIC):
            unprotect(content, asset.filename, asset.device_id)
            continue
        # Atomic replacement makes an interrupted offline upgrade safe to rerun.
        descriptor, name = tempfile.mkstemp(prefix='.media-upgrade-', dir=root)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, 'wb') as output:
                output.write(protect(content, asset.filename, asset.device_id))
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
