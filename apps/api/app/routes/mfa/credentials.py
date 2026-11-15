"""Credentials HTTP endpoints; registered on the shared MFA blueprint."""

from app.time_contract import timestamp as serialize_time
from flask import request, jsonify
from app.extensions import db
from app.authorization import revoke_access
from app.validation import totp_code as validate_totp_code
from app.models import MFACredential, User
from flask_jwt_extended import jwt_required, get_jwt_identity
import pyotp
from app.authenticators import pending_credential, activate_credential, lock_account, consume_totp
from . import mfa_bp


@mfa_bp.route("/mfa/bind/totp", methods=["POST"])
@jwt_required()
def bind_totp():
    """绑定TOTP（生成密钥和二维码URI）"""
    username = get_jwt_identity()
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"msg": "User not found"}), 404

    # 检查是否已绑定
    existing = MFACredential.query.filter_by(
        user_id=user.id, credential_type="totp", is_active=True
    ).first()
    if existing:
        return jsonify({"msg": "TOTP already bound"}), 400

    # 生成TOTP密钥
    credential = pending_credential(user)
    if credential is None:
        db.session.rollback()
        return jsonify(msg="TOTP already bound"), 409
    secret = credential.credential_data
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=username, issuer_name="SmartLock")

    # 保存到数据库（待验证状态）
    db.session.commit()

    return jsonify(
        {
            "msg": "TOTP secret generated",
            "secret": secret,
            "qr_uri": uri,
            "credential_id": credential.id,
        }
    ), 200


@mfa_bp.route("/mfa/verify/totp", methods=["POST"])
@jwt_required()
def verify_totp():
    """验证TOTP码（用于绑定确认或开门认证）"""
    data = request.get_json() or {}
    code = validate_totp_code(data)
    credential_id = data.get("credential_id")  # 绑定时需要
    if credential_id is not None and (type(credential_id) is not int or credential_id <= 0):
        return jsonify(msg="credential_id must be a positive integer"), 400

    username = get_jwt_identity()
    user = User.query.filter_by(username=username).first()

    if credential_id:
        lock_account(user.id)
        # 绑定确认场景
        credential = db.session.get(MFACredential, credential_id)
        if not credential or credential.user_id != user.id or credential.credential_type != "totp":
            return jsonify({"msg": "Invalid credential"}), 400
    else:
        # 开门认证场景
        credential = MFACredential.query.filter_by(
            user_id=user.id, credential_type="totp", is_active=True
        ).first()
        if not credential:
            return jsonify({"msg": "TOTP not bound"}), 400

    # 验证TOTP码
    if not consume_totp(credential, code):
        return jsonify(msg="Invalid or already used TOTP code"), 401

    # 绑定确认：激活凭证
    if credential_id and not credential.is_active:
        if not activate_credential(user, credential):
            db.session.rollback()
            return jsonify(msg="Enrollment expired or authenticator already bound"), 409
        db.session.commit()
        return jsonify({"msg": "TOTP bound successfully"}), 200

    db.session.commit()
    return jsonify({"msg": "TOTP verified"}), 200


@mfa_bp.route("/mfa/status", methods=["GET"])
@jwt_required()
def mfa_status():
    username = get_jwt_identity()
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"msg": "User not found"}), 404

    totp = MFACredential.query.filter_by(
        user_id=user.id,
        credential_type="totp",
        is_active=True,
    ).first()
    devices = MFACredential.query.filter_by(
        user_id=user.id,
        credential_type="device",
        is_active=True,
    ).all()

    return jsonify(
        {
            "totp_bound": bool(totp),
            "devices": [
                {
                    "credential_id": device.id,
                    "device_id": device.device_id,
                    "is_active": device.is_active,
                    "created_at": serialize_time(device.created_at) if device.created_at else None,
                }
                for device in devices
            ],
        }
    ), 200


@mfa_bp.route("/mfa/unbind/totp", methods=["POST"])
@jwt_required()
def unbind_totp():
    code = validate_totp_code(request.get_json() or {})
    username = get_jwt_identity()
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"msg": "User not found"}), 404

    credentials = MFACredential.query.filter_by(
        user_id=user.id,
        credential_type="totp",
        is_active=True,
    ).all()
    if not credentials or not consume_totp(credentials[0], code):
        return jsonify(msg="Invalid or already used TOTP code"), 401
    for credential in credentials:
        credential.is_active = False
        credential.credential_data = pyotp.random_base32()
        credential.last_totp_counter = -1
    revoke_access(user.id)
    db.session.commit()

    return jsonify({"msg": "TOTP unbound successfully"}), 200
