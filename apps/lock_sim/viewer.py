"""Domain-separated credentials for the simulator's read-only display."""

import hashlib
import hmac


def viewer_token(secret):
    """Derive a display credential without disclosing the command signing key."""
    return hmac.new(secret.encode(), b"smartlock/lock-sim/viewer/v1", hashlib.sha256).hexdigest()
