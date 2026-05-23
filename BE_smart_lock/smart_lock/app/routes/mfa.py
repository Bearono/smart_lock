from flask import Blueprint, request, jsonify
from app import db
from app.models import (
    AccessLog,
    AuthSession,
    FaceRecognitionLog,
    GuestPass,
    MFACredential,
    UnlockToken,
    User,
)
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timedelta
import pyotp
import secrets
import hashlib
from .secure_payload import decrypt_secure_payload

mfa_bp = Blueprint('mfa', __name__)

# ==================== TOTP 绑定与验证 ====================

@mfa_bp.route('/mfa/bind/totp', methods=['POST'])
@jwt_required()
def bind_totp():
    """绑定TOTP（生成密钥和二维码URI）"""
    username = get_jwt_identity()
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"msg": "User not found"}), 404

    # 检查是否已绑定
    existing = MFACredential.query.filter_by(
        user_id=user.id,
        credential_type='totp',
        is_active=True
    ).first()
    if existing:
        return jsonify({"msg": "TOTP already bound"}), 400

    # 生成TOTP密钥
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=username, issuer_name="SmartLock")

    # 保存到数据库（待验证状态）
    credential = MFACredential(
        user_id=user.id,
        credential_type='totp',
        credential_data=secret,
        is_active=False  # 需要验证后激活
    )
    db.session.add(credential)
    db.session.commit()

    return jsonify({
        "msg": "TOTP secret generated",
        "secret": secret,
        "qr_uri": uri,
        "credential_id": credential.id
    }), 200


@mfa_bp.route('/mfa/verify/totp', methods=['POST'])
@jwt_required()
def verify_totp():
    """验证TOTP码（用于绑定确认或开门认证）"""
    data = request.get_json()
    code = data.get('code')
    credential_id = data.get('credential_id')  # 绑定时需要

    username = get_jwt_identity()
    user = User.query.filter_by(username=username).first()

    if credential_id:
        # 绑定确认场景
        credential = MFACredential.query.get(credential_id)
        if not credential or credential.user_id != user.id:
            return jsonify({"msg": "Invalid credential"}), 400
    else:
        # 开门认证场景
        credential = MFACredential.query.filter_by(
            user_id=user.id,
            credential_type='totp',
            is_active=True
        ).first()
        if not credential:
            return jsonify({"msg": "TOTP not bound"}), 400

    # 验证TOTP码
    totp = pyotp.TOTP(credential.credential_data)
    if not totp.verify(code, valid_window=1):  # 容错±30秒
        return jsonify({"msg": "Invalid TOTP code"}), 401

    # 绑定确认：激活凭证
    if credential_id and not credential.is_active:
        credential.is_active = True
        db.session.commit()
        return jsonify({"msg": "TOTP bound successfully"}), 200

    return jsonify({"msg": "TOTP verified"}), 200


@mfa_bp.route('/mfa/status', methods=['GET'])
@jwt_required()
def mfa_status():
    username = get_jwt_identity()
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"msg": "User not found"}), 404

    totp = MFACredential.query.filter_by(
        user_id=user.id,
        credential_type='totp',
        is_active=True,
    ).first()
    devices = MFACredential.query.filter_by(
        user_id=user.id,
        credential_type='device',
        is_active=True,
    ).all()

    return jsonify({
        "totp_bound": bool(totp),
        "devices": [
            {
                "credential_id": device.id,
                "device_id": device.device_id,
                "is_active": device.is_active,
                "created_at": device.created_at.strftime("%Y-%m-%d %H:%M:%S") if device.created_at else None,
            }
            for device in devices
        ],
    }), 200


@mfa_bp.route('/mfa/unbind/totp', methods=['POST'])
@jwt_required()
def unbind_totp():
    username = get_jwt_identity()
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"msg": "User not found"}), 404

    credentials = MFACredential.query.filter_by(
        user_id=user.id,
        credential_type='totp',
        is_active=True,
    ).all()
    for credential in credentials:
        credential.is_active = False
    db.session.commit()

    return jsonify({"msg": "TOTP unbound successfully"}), 200


# ==================== 设备绑定 ====================

@mfa_bp.route('/mfa/bind/device', methods=['POST'])
@jwt_required()
def bind_device():
    """绑定设备（存储设备ID和公钥）"""
    data = request.get_json()
    device_id = data.get('device_id')
    device_pubkey = data.get('device_pubkey')  # 设备公钥（可选）

    username = get_jwt_identity()
    user = User.query.filter_by(username=username).first()

    # 检查设备是否已绑定
    existing = MFACredential.query.filter_by(
        user_id=user.id,
        credential_type='device',
        device_id=device_id,
        is_active=True
    ).first()
    if existing:
        return jsonify({"msg": "Device already bound"}), 400

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


# ==================== 开门认证流程 ====================

@mfa_bp.route('/mfa/unbind/device', methods=['POST'])
@jwt_required()
def unbind_device():
    data = request.get_json() or {}
    device_id = data.get('device_id')
    if not device_id:
        return jsonify({"msg": "device_id is required"}), 400

    username = get_jwt_identity()
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"msg": "User not found"}), 404

    credential = MFACredential.query.filter_by(
        user_id=user.id,
        credential_type='device',
        device_id=device_id,
        is_active=True,
    ).first()
    if not credential:
        return jsonify({"msg": "Device binding not found"}), 404

    credential.is_active = False
    db.session.commit()

    return jsonify({"msg": "Device unbound successfully"}), 200


@mfa_bp.route('/mfa/open-door/request', methods=['POST'])
@jwt_required()
def open_door_request():
    """发起开门请求（创建认证会话）"""
    data = request.get_json()
    device_id = data.get('device_id')

    username = get_jwt_identity()
    user = User.query.filter_by(username=username).first()

    # 验证设备绑定
    device_bound = MFACredential.query.filter_by(
        user_id=user.id,
        credential_type='device',
        device_id=device_id,
        is_active=True
    ).first()
    if not device_bound:
        return jsonify({"msg": "Device not bound"}), 403

    # 创建认证会话
    request_id = secrets.token_hex(32)
    nonce = secrets.token_hex(32)

    session = AuthSession(
        request_id=request_id,
        user_id=user.id,
        nonce=nonce,
        status='pending',
        device_verified=True,  # 设备已验证
        expires_at=datetime.now() + timedelta(minutes=5)
    )
    db.session.add(session)
    db.session.commit()

    return jsonify({
        "msg": "Auth session created",
        "request_id": request_id,
        "nonce": nonce,
        "requires_face": True,
        "requires_totp": _check_totp_required(user.id)
    }), 200


@mfa_bp.route('/mfa/open-door/face-result', methods=['POST'])
def receive_face_result():
    """接收树莓派上传的人脸识别结果"""
    data = request.get_json() or {}
    if 'payload' in data and 'enc_key' in data:
        try:
            data = decrypt_secure_payload(data)
        except Exception as exc:
            return jsonify({"msg": "Invalid encrypted payload", "detail": str(exc)}), 400

    request_id = data.get('request_id')
    face_user_id = data.get('face_user_id')
    similarity_score = data.get('similarity_score')
    device_id = data.get('device_id')

    # 查找认证会话
    session = AuthSession.query.filter_by(request_id=request_id).first()
    if not session:
        return jsonify({"msg": "Invalid request_id"}), 404

    if session.status != 'pending':
        return jsonify({"msg": "Session already processed"}), 400

    # 验证人脸结果
    user = User.query.get(session.user_id)
    passed = face_user_id == user.username and similarity_score >= 0.7
    db.session.add(FaceRecognitionLog(
        request_id=request_id,
        device_id=device_id,
        expected_username=user.username if user else None,
        face_user_id=face_user_id,
        similarity_score=similarity_score,
        passed=passed,
        snapshot_path=data.get('snapshot'),
        failure_reason=None if passed else 'face_user_or_score_mismatch',
    ))

    if passed:
        session.face_verified = True
        session.face_user_id = face_user_id
        session.similarity_score = similarity_score
        session.status = 'face_verified'
        db.session.commit()

        return jsonify({
            "msg": "Face verified",
            "requires_totp": _check_totp_required(user.id)
        }), 200
    else:
        session.status = 'failed'
        db.session.commit()
        return jsonify({"msg": "Face verification failed"}), 401


@mfa_bp.route('/mfa/open-door/confirm', methods=['POST'])
@jwt_required()
def open_door_confirm():
    """确认开门（汇总所有因子，签发开门令牌）"""
    data = request.get_json()
    request_id = data.get('request_id')
    totp_code = data.get('totp_code')  # 如果需要TOTP

    username = get_jwt_identity()
    user = User.query.filter_by(username=username).first()

    # 查找认证会话
    session = AuthSession.query.filter_by(request_id=request_id, user_id=user.id).first()
    if not session:
        return jsonify({"msg": "Invalid session"}), 404

    if session.status == 'failed':
        return jsonify({"msg": "Authentication failed"}), 401

    # 检查是否需要TOTP
    if _check_totp_required(user.id):
        if not totp_code:
            return jsonify({"msg": "TOTP code required"}), 400

        # 验证TOTP
        credential = MFACredential.query.filter_by(
            user_id=user.id,
            credential_type='totp',
            is_active=True
        ).first()
        totp = pyotp.TOTP(credential.credential_data)
        if not totp.verify(totp_code, valid_window=1):
            session.status = 'failed'
            db.session.commit()
            return jsonify({"msg": "Invalid TOTP code"}), 401

        session.totp_verified = True

    # 所有因子验证通过，签发开门令牌
    if session.device_verified and session.face_verified:
        token = secrets.token_urlsafe(64)
        unlock_token = UnlockToken(
            token=token,
            user_id=user.id,
            request_id=request_id,
            expires_at=datetime.now() + timedelta(seconds=60)
        )
        db.session.add(unlock_token)

        session.status = 'completed'
        db.session.commit()

        # 记录访问日志
        log = AccessLog(action='UNLOCK', username=username)
        db.session.add(log)
        db.session.commit()

        return jsonify({
            "msg": "Authentication successful",
            "unlock_token": token,
            "expires_in": 60
        }), 200

    return jsonify({"msg": "Authentication incomplete"}), 400


# ==================== 访客授权 ====================

@mfa_bp.route('/mfa/guest/create', methods=['POST'])
@jwt_required()
def create_guest_pass():
    """创建访客临时授权"""
    data = request.get_json()
    guest_name = data.get('guest_name')
    valid_hours = data.get('valid_hours', 24)
    max_uses = data.get('max_uses', 1)

    username = get_jwt_identity()
    user = User.query.filter_by(username=username).first()

    # 生成授权码
    pass_code = secrets.token_urlsafe(16)
    pass_hash = hashlib.sha256(pass_code.encode()).hexdigest()

    guest_pass = GuestPass(
        pass_code=pass_hash,
        created_by=user.id,
        guest_name=guest_name,
        valid_from=datetime.now(),
        valid_until=datetime.now() + timedelta(hours=valid_hours),
        max_uses=max_uses
    )
    db.session.add(guest_pass)
    db.session.commit()

    return jsonify({
        "msg": "Guest pass created",
        "pass_code": pass_code,  # 明文返回给用户（仅此一次）
        "valid_until": guest_pass.valid_until.isoformat(),
        "max_uses": max_uses
    }), 200


@mfa_bp.route('/mfa/guest/verify', methods=['POST'])
def verify_guest_pass():
    """验证访客授权码并开门"""
    data = request.get_json()
    pass_code = data.get('pass_code')

    pass_hash = hashlib.sha256(pass_code.encode()).hexdigest()
    guest_pass = GuestPass.query.filter_by(pass_code=pass_hash, is_active=True).first()

    if not guest_pass:
        return jsonify({"msg": "Invalid pass code"}), 401

    # 检查有效期
    now = datetime.now()
    if now < guest_pass.valid_from or now > guest_pass.valid_until:
        return jsonify({"msg": "Pass code expired"}), 401

    # 检查使用次数
    if guest_pass.used_count >= guest_pass.max_uses:
        return jsonify({"msg": "Pass code usage limit reached"}), 401

    # 签发开门令牌
    token = secrets.token_urlsafe(64)
    unlock_token = UnlockToken(
        token=token,
        user_id=guest_pass.created_by,
        request_id=f"guest_{guest_pass.id}",
        expires_at=datetime.now() + timedelta(seconds=60)
    )
    db.session.add(unlock_token)

    guest_pass.used_count += 1
    db.session.commit()

    # 记录访问日志
    log = AccessLog(action='GUEST_UNLOCK', username=guest_pass.guest_name or 'Guest')
    db.session.add(log)
    db.session.commit()

    return jsonify({
        "msg": "Guest pass verified",
        "unlock_token": token,
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

    guest_pass = GuestPass.query.get(pass_id)
    if not guest_pass or guest_pass.created_by != user.id:
        return jsonify({"msg": "Pass not found"}), 404

    guest_pass.is_active = False
    db.session.commit()

    return jsonify({"msg": "Guest pass revoked"}), 200


# ==================== 辅助函数 ====================

def _check_totp_required(user_id):
    """判断是否需要TOTP（根据时间段或风险等级）"""
    # 简单策略：如果用户绑定了TOTP，深夜时段（22:00-6:00）需要验证
    credential = MFACredential.query.filter_by(
        user_id=user_id,
        credential_type='totp',
        is_active=True
    ).first()

    if not credential:
        return False

    hour = datetime.now().hour
    if hour >= 22 or hour < 6:
        return True

    return False
