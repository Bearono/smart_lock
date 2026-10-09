"""Shared device authorization and transaction helpers for the door flow."""
from sqlalchemy import func
from app import db
from app.models import MFACredential, DeviceGrant


def device_binding(user_id, device_id):
    if not device_id:
        return None
    if not DeviceGrant.query.filter_by(user_id=user_id, device_id=device_id).first():
        return None
    return MFACredential.query.filter_by(
        user_id=user_id, credential_type='device', device_id=device_id, is_active=True
    ).order_by(MFACredential.is_locked.desc(), MFACredential.id.asc()).first()


def record_failure(user_id, device_id):
    credentials = MFACredential.query.filter_by(
        user_id=user_id, credential_type='device', device_id=device_id, is_active=True)
    count = func.coalesce(MFACredential.failed_attempts, 0) + 1
    credentials.update({MFACredential.failed_attempts: count}, synchronize_session=False)
    newly_locked = credentials.filter(
        MFACredential.is_locked.is_not(True), MFACredential.failed_attempts >= 5,
    ).update({MFACredential.is_locked: True}, synchronize_session='fetch')
    if newly_locked:
        from app.models import AlarmLog, User
        from app.notifications import queue_alarm
        user = db.session.get(User, user_id)
        alarm = AlarmLog(alarm_type='AUTH_LOCKOUT',
            message=f'账户 {user.username if user else user_id} 连续认证失败，已暂停其对设备 {device_id} 的开门权限，请核查后解除锁定。')
        db.session.add(alarm)
        queue_alarm(alarm)
    if credentials.filter(MFACredential.is_locked.is_(True)).first():
        from app.authorization import revoke_access
        revoke_access(user_id, device_id)


def reset_failures(user_id, device_id):
    MFACredential.query.filter_by(
        user_id=user_id, credential_type='device', device_id=device_id, is_active=True,
    ).update({MFACredential.failed_attempts: 0}, synchronize_session=False)
