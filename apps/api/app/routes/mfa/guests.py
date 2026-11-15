"""Guests HTTP endpoints; registered on the shared MFA blueprint."""
from app.time_contract import timestamp as serialize_time
from flask import request, jsonify
from app import db
from app.door_auth import device_binding
from app.authorization import revoke_guest
from app.validation import text_field
from app.models import AccessLog, GuestPass, UnlockToken, User
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timedelta
import secrets
import hashlib
from . import mfa_bp


@mfa_bp.route('/mfa/guest/create', methods=['POST'])
@jwt_required()
def create_guest_pass():
    """创建访客临时授权"""
    data = request.get_json() or {}
    device_id = text_field(data, 'device_id', maximum=50)
    guest_name = text_field(data, 'guest_name', maximum=80, required=False)
    valid_hours = data.get('valid_hours', 24)
    max_uses = data.get('max_uses', 1)

    username = get_jwt_identity()
    user = User.query.filter_by(username=username).first()
    binding = device_binding(user.id, device_id)
    if not binding or binding.is_locked:
        return jsonify(msg='Active device binding required'), 403
    if (type(valid_hours) is not int or not 1 <= valid_hours <= 168
            or type(max_uses) is not int or not 1 <= max_uses <= 100):
        return jsonify(msg='valid_hours must be 1-168 and max_uses 1-100'), 400

    # 生成授权码
    pass_code = secrets.token_urlsafe(16)
    pass_hash = hashlib.sha256(pass_code.encode()).hexdigest()

    guest_pass = GuestPass(
        pass_code=pass_hash,
        created_by=user.id,
        guest_name=guest_name,
        device_id=device_id,
        valid_from=datetime.now(),
        valid_until=datetime.now() + timedelta(hours=valid_hours),
        max_uses=max_uses
    )
    db.session.add(guest_pass)
    db.session.add(AccessLog(action='GUEST_PASS_CREATED', username=username, device_id=device_id))
    db.session.commit()

    return jsonify({
        "msg": "Guest pass created",
        "pass_code": pass_code,  # 明文返回给用户（仅此一次）
        "valid_until": serialize_time(guest_pass.valid_until),
        "max_uses": max_uses
    }), 200


@mfa_bp.route('/mfa/guest/verify', methods=['POST'])
def verify_guest_pass():
    """验证访客授权码并开门"""
    data = request.get_json() or {}
    pass_code = data.get('pass_code')
    if not isinstance(pass_code, str) or not pass_code:
        return jsonify(msg='pass_code is required'), 400

    pass_hash = hashlib.sha256(pass_code.encode()).hexdigest()
    guest_pass = GuestPass.query.filter_by(pass_code=pass_hash, is_active=True).first()

    if not guest_pass:
        return jsonify({"msg": "Invalid pass code"}), 401
    owner = db.session.get(User, guest_pass.created_by)
    binding = device_binding(guest_pass.created_by, guest_pass.device_id)
    if not owner or owner.status != 'approved' or not binding or binding.is_locked:
        return jsonify(msg='Guest authorization revoked'), 403

    # 检查有效期
    now = datetime.now()
    if now < guest_pass.valid_from or now > guest_pass.valid_until:
        return jsonify({"msg": "Pass code expired"}), 401

    # 检查使用次数
    if guest_pass.used_count >= guest_pass.max_uses:
        return jsonify({"msg": "Pass code usage limit reached"}), 401

    claimed = GuestPass.query.filter(
        GuestPass.id == guest_pass.id, GuestPass.is_active.is_(True),
        GuestPass.valid_from <= now, GuestPass.valid_until > now,
        GuestPass.used_count < GuestPass.max_uses,
    ).update({GuestPass.used_count: GuestPass.used_count + 1}, synchronize_session=False)
    if not claimed:
        db.session.rollback()
        return jsonify(msg='Guest pass expired, revoked or exhausted'), 409

    # 签发开门令牌
    token = secrets.token_urlsafe(64)
    unlock_token = UnlockToken(
        token=token,
        user_id=guest_pass.created_by,
        request_id=f"guest_{guest_pass.id}",
        device_id=guest_pass.device_id,
        expires_at=datetime.now() + timedelta(seconds=60)
    )
    db.session.add(unlock_token)

    # 记录访问日志
    log = AccessLog(action='GUEST_TOKEN_ISSUED', username=guest_pass.guest_name or 'Guest', device_id=guest_pass.device_id)
    db.session.add(log)
    db.session.commit()

    return jsonify({
        "msg": "Guest pass verified",
        "unlock_token": token,
        "device_id": guest_pass.device_id,
        "expires_in": 60
    }), 200


@mfa_bp.route('/mfa/guest/list', methods=['GET'])
@jwt_required()
def list_guest_passes():
    username = get_jwt_identity()
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"msg": "User not found"}), 404

    passes = GuestPass.query.filter_by(created_by=user.id).order_by(GuestPass.id.desc()).all()
    return jsonify([guest_pass.to_dict() for guest_pass in passes]), 200


@mfa_bp.route('/mfa/guest/revoke/<int:pass_id>', methods=['POST'])
@jwt_required()
def revoke_guest_pass(pass_id):
    """撤销访客授权"""
    username = get_jwt_identity()
    user = User.query.filter_by(username=username).first()

    guest_pass = db.session.get(GuestPass, pass_id)
    if not guest_pass or guest_pass.created_by != user.id:
        return jsonify({"msg": "Pass not found"}), 404

    revoke_guest(guest_pass)
    db.session.add(AccessLog(action='GUEST_PASS_REVOKED', username=username, device_id=guest_pass.device_id))
    db.session.commit()

    return jsonify({"msg": "Guest pass revoked"}), 200
