"""Bindings HTTP endpoints; registered on the shared MFA blueprint."""
from flask import request, jsonify
from app import db
from app.authorization import revoke_access
from app.validation import text_field
from app.models import AccessLog, MFACredential, User
from flask_jwt_extended import jwt_required, get_jwt_identity
from . import mfa_bp


@mfa_bp.route('/mfa/bind/device', methods=['POST'])
@jwt_required()
def bind_device():
    """绑定设备（存储设备ID和公钥）"""
    data = request.get_json() or {}
    device_id = data.get('device_id')
    if not isinstance(device_id, str) or not device_id or len(device_id) > 50:
        return jsonify(msg='Valid device_id is required'), 400
    device_pubkey = data.get('device_pubkey', '')
    if not isinstance(device_pubkey, str) or len(device_pubkey) > 500:
        return jsonify(msg='device_pubkey must be a string of at most 500 characters'), 400

    username = get_jwt_identity()
    user = User.query.filter_by(username=username).first()

    # 检查设备是否已绑定
    from app.models import DeviceGrant
    if not DeviceGrant.query.filter_by(user_id=user.id, device_id=device_id).first():
        return jsonify(msg='Administrator must grant device access before binding'), 403
    existing = MFACredential.query.filter_by(
        user_id=user.id,
        credential_type='device',
        device_id=device_id,
    ).order_by(MFACredential.is_locked.desc(), MFACredential.id.asc()).first()
    if existing:
        # Rebinding must never reset a security lockout.
        existing.is_active = True
        db.session.commit()
        return jsonify({"msg": "Device bound successfully"}), 200

    credential = MFACredential(
        user_id=user.id,
        credential_type='device',
        credential_data=device_pubkey or '',
        device_id=device_id,
        is_active=True
    )
    db.session.add(credential)
    db.session.commit()

    return jsonify({"msg": "Device bound successfully"}), 200


@mfa_bp.route('/mfa/unbind/device', methods=['POST'])
@jwt_required()
def unbind_device():
    data = request.get_json() or {}
    device_id = text_field(data, 'device_id', maximum=50)

    username = get_jwt_identity()
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"msg": "User not found"}), 404

    credentials = MFACredential.query.filter_by(
        user_id=user.id,
        credential_type='device',
        device_id=device_id,
        is_active=True,
    )
    if not credentials.first():
        return jsonify({"msg": "Device binding not found"}), 404

    credentials.update({MFACredential.is_active: False}, synchronize_session=False)
    revoke_access(user.id, device_id)
    db.session.commit()

    return jsonify({"msg": "Device unbound successfully"}), 200


@mfa_bp.route('/mfa/admin/device/unlock', methods=['POST'])
@jwt_required()
def admin_unlock_device():
    """管理员介入：解除特定用户的设备锁定"""
    admin_name = get_jwt_identity()
    admin_user = User.query.filter_by(username=admin_name).first()
    if not admin_user or admin_user.role != 'admin':
        return jsonify({"msg": "Admin privilege required"}), 403

    data = request.get_json() or {}
    target_username = text_field(data, 'target_username', maximum=80)

    target_user = User.query.filter_by(username=target_username).first()
    if not target_user:
        return jsonify({"msg": "Target user not found"}), 404

    device_creds = MFACredential.query.filter_by(
        user_id=target_user.id, credential_type='device'
    ).all()

    if not device_creds:
        return jsonify({"msg": "No device bound to this user"}), 404

    # 执行解锁
    for device_cred in device_creds:
        device_cred.failed_attempts = 0
        device_cred.is_locked = False
    log = AccessLog(action=f'ADMIN_UNLOCK_DEVICE_FOR_{target_username}', username=admin_name)
    db.session.add(log)
    db.session.commit()

    return jsonify({"msg": f"Device for {target_username} has been successfully unlocked."}), 200
