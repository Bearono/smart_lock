"""Generate persistent local Compose secrets once; never print or replace them."""
from pathlib import Path
import os
import secrets

root = Path(__file__).resolve().parent / 'secrets'
root.mkdir(mode=0o700, exist_ok=True)
for name in ('app_key', 'jwt_key'):
    path = root / name
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        continue
    with os.fdopen(descriptor, 'w') as output:
        output.write(secrets.token_hex(32))
    # The enclosing host directory is private; the container's unprivileged UID needs read access.
    path.chmod(0o444)
print('Persistent secrets are ready. Back them up securely with the database.')
