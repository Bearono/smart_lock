"""Existing authenticated HTTP command wire format, shared by device adapters."""

import hashlib
import hmac
import json
import secrets
import time


def signature(secret, method, path, stamp, nonce, body):
    message = json.dumps(
        [method, path, stamp, nonce, hashlib.sha256(body).hexdigest()], separators=(",", ":")
    ).encode()
    key = hashlib.sha256(b"smart-lock-backend-command\0" + secret.encode()).digest()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def sign(secret, path, payload, *, now=None, nonce=None):
    body = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode()
    stamp = str(int(time.time() if now is None else now))
    nonce = nonce or secrets.token_hex(16)
    return body, {
        "Content-Type": "application/json",
        "X-Command-Time": stamp,
        "X-Command-Nonce": nonce,
        "X-Command-Signature": signature(secret, "POST", path, stamp, nonce, body),
    }


def verify(secret, method, path, body, headers, *, now=None):
    now = time.time() if now is None else now
    stamp, nonce, supplied = (
        headers.get(key, "") for key in ("X-Command-Time", "X-Command-Nonce", "X-Command-Signature")
    )
    if (
        not stamp.isascii()
        or not stamp.isdigit()
        or len(stamp) > 12
        or abs(now - int(stamp)) > 60
        or len(nonce) != 32
        or any(c not in "0123456789abcdef" for c in nonce)
        or len(supplied) != 64
        or any(c not in "0123456789abcdef" for c in supplied)
    ):
        raise ValueError("Authenticated command required")
    expected = signature(secret, method, path, stamp, nonce, body)
    if not hmac.compare_digest(supplied, expected):
        raise ValueError("Invalid command signature")
    return nonce, int(stamp) + 60
