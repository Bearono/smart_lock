"""Memory-hard new password hashes, with in-transaction upgrade of legacy bcrypt."""

from werkzeug.security import generate_password_hash, check_password_hash
from threading import BoundedSemaphore
from app.extensions import bcrypt

METHOD = "scrypt:131072:8:1"
# Each scrypt operation needs roughly 128 MiB. Bound it per worker so the two
# production workers fit the 512 MiB container even with concurrent HTTP requests.
_scrypt_slot = BoundedSemaphore(1)


def hash_password(password):
    with _scrypt_slot:
        return generate_password_hash(password, method=METHOD, salt_length=16)


def verify_password(user, password):
    if not user or not isinstance(password, str) or not password or len(password.encode()) > 72:
        return False
    old = user.password_hash
    try:
        if old.startswith(("$2a$", "$2b$", "$2y$")):
            valid = bcrypt.check_password_hash(old, password)
        else:
            with _scrypt_slot:
                valid = check_password_hash(old, password)
    except (ValueError, TypeError):
        return False
    if valid and not old.startswith(METHOD + "$"):
        user.password_hash = hash_password(password)
    return valid
