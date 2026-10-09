"""Serialize authenticator enrollment and retire alternative pending secrets."""
from datetime import datetime, timedelta
import pyotp
from app import db
from app.models import AccessLog, LoginChallenge, MFACredential, User

ENROLLMENT_TTL = timedelta(minutes=5)


def lock_account(user_id):
    # A real UPDATE locks the account row across workers without changing its version.
    User.query.filter_by(id=user_id).update(
        {User.auth_version: User.auth_version}, synchronize_session=False)


def pending_credential(user):
    lock_account(user.id)
    credentials = MFACredential.query.filter_by(user_id=user.id, credential_type='totp')
    if credentials.filter_by(is_active=True).first():
        return None
    credential = credentials.order_by(MFACredential.id).first()
    now = datetime.now()
    if credential is None:
        credential = MFACredential(user_id=user.id, credential_type='totp',
                                   credential_data=pyotp.random_base32(), is_active=False,
                                   created_at=now)
        db.session.add(credential)
        db.session.flush()
    elif not credential.created_at or now - credential.created_at >= ENROLLMENT_TTL:
        credential.credential_data = pyotp.random_base32()
        credential.created_at = now
        LoginChallenge.query.filter_by(credential_id=credential.id).update(
            {'consumed': True}, synchronize_session='fetch')
    return credential


def activate_credential(user, credential):
    lock_account(user.id)
    db.session.refresh(credential)
    if (credential.user_id != user.id or credential.credential_type != 'totp'
            or credential.is_active or not credential.created_at
            or datetime.now() - credential.created_at >= ENROLLMENT_TTL):
        return False
    if MFACredential.query.filter(
        MFACredential.user_id == user.id, MFACredential.credential_type == 'totp',
        MFACredential.is_active.is_(True), MFACredential.id != credential.id,
    ).first():
        return False
    credential.is_active = True
    # Historical duplicate pending enrollments can never replace the bound authenticator.
    for other in MFACredential.query.filter(
        MFACredential.user_id == user.id, MFACredential.credential_type == 'totp',
        MFACredential.id != credential.id,
    ).all():
        other.is_active = False
        other.credential_data = pyotp.random_base32()
    db.session.add(AccessLog(username=user.username, action='TOTP_BOUND'))
    return True
