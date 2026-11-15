"""User-to-device grants are issued by operators, never by knowledge of a device ID."""
from flask import abort
from flask_jwt_extended import get_jwt_identity
from app.models import DeviceGrant, User


def current_user():
    return User.query.filter_by(username=get_jwt_identity()).one()


def permitted_devices(user=None):
    user = user or current_user()
    return DeviceGrant.query.filter_by(user_id=user.id).with_entities(DeviceGrant.device_id)


def require_device(device_id):
    user = current_user()
    if user.role != 'admin' and not DeviceGrant.query.filter_by(user_id=user.id, device_id=device_id).first():
        abort(403, description='Device access has not been granted')
    return user
