"""Shared operator grant changes for web administration and CLI commands."""
from app import db
from app.authorization import revoke_access
from app.models import AccessLog, DeviceGrant, DeviceProvisioning, MFACredential
from app.provisioning import validate_device_id


def set_device_grant(user, device_id, *, granted, actor):
    """Apply grant and all dependent invalidations in the caller's transaction."""
    if not validate_device_id(device_id):
        raise ValueError('Invalid device ID')
    provision = db.session.get(DeviceProvisioning, device_id)
    if granted and (user.status != 'approved' or not provision or not provision.enabled):
        raise ValueError('Approved user and enabled provisioned device are required')
    grant = db.session.get(DeviceGrant, (user.id, device_id))
    if granted:
        if grant is None:
            db.session.add(DeviceGrant(user_id=user.id, device_id=device_id))
    else:
        revoke_access(user.id, device_id)
        if grant is not None:
            db.session.delete(grant)
        MFACredential.query.filter_by(
            user_id=user.id, device_id=device_id, credential_type='device',
        ).update({'is_active': False}, synchronize_session='fetch')
    action = 'GRANT' if granted else 'REVOKE'
    db.session.add(AccessLog(username=actor, action=f'{action}:{user.username}:{device_id}'[:100]))
