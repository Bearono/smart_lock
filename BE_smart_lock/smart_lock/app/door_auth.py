"""Shared device authorization and transaction helpers for the door flow."""
from sqlalchemy import case, func
from app import db
from app.models import MFACredential


def device_binding(user_id, device_id):
    if not device_id:
        return None
    return MFACredential.query.filter_by(
        user_id=user_id, credential_type='device', device_id=device_id, is_active=True
    ).order_by(MFACredential.is_locked.desc(), MFACredential.id.asc()).first()


def record_failure(user_id, device_id):
    credentials = MFACredential.query.filter_by(
        user_id=user_id, credential_type='device', device_id=device_id, is_active=True)
    count = func.coalesce(MFACredential.failed_attempts, 0) + 1
    credentials.update({MFACredential.failed_attempts: count,
                        MFACredential.is_locked: case((count >= 5, True), else_=MFACredential.is_locked)},
                       synchronize_session=False)


def reset_failures(user_id, device_id):
    MFACredential.query.filter_by(
        user_id=user_id, credential_type='device', device_id=device_id, is_active=True,
    ).update({MFACredential.failed_attempts: 0}, synchronize_session=False)
