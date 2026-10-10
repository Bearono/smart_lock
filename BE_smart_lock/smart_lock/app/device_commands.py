"""Canonical authenticated commands for operator-provisioned device services."""
import hashlib
import hmac
import json
import secrets
import time
from app.provisioning import device_password


def signed_command(device_id, path, payload):
    body = json.dumps(payload, separators=(',', ':')).encode()
    stamp, nonce = str(int(time.time())), secrets.token_hex(16)
    message = json.dumps(['POST', path, stamp, nonce, hashlib.sha256(body).hexdigest()],
                         separators=(',', ':')).encode()
    key = hashlib.sha256(b'smart-lock-backend-command\0' + device_password(device_id).encode()).digest()
    return body, {'Content-Type': 'application/json', 'X-Command-Time': stamp,
                  'X-Command-Nonce': nonce,
                  'X-Command-Signature': hmac.new(key, message, hashlib.sha256).hexdigest()}
