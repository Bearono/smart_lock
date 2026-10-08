"""Account credential changes revoke derived capabilities before commit."""
import pyotp

from app import bcrypt, db
from app.authorization import revoke_access
from app.models import AccessLog, MFACredential
from app.validation import validate_password


def change_password(user, password, *, actor, reset_totp=False):
    validate_password(password)
    user.password_hash = bcrypt.generate_password_hash(password).decode()
    revoke_access(user.id)
    if reset_totp:
        for credential in MFACredential.query.filter_by(user_id=user.id, credential_type='totp').all():
            credential.is_active = False
            credential.credential_data = pyotp.random_base32()
    action = 'ACCOUNT_RECOVERY' if reset_totp else 'PASSWORD_CHANGE'
    db.session.add(AccessLog(username=actor, action=f'{action}:{user.username}'[:100]))
