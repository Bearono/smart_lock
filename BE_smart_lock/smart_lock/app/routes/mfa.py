import os
import math
import requests
from flask import Blueprint, request, jsonify, current_app
from app import db
from app.door_auth import device_binding, record_failure, reset_failures
from app.models import (
    AccessLog,
    AuthSession,
    Device,
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
from .secure_receiver import save_snapshot_image
from .secure_payload import decrypt_secure_payload
from .security_protocol import PROTOCOL_VERSION

mfa_bp = Blueprint('mfa', __name__)


class DeviceUnavailable(RuntimeError):
    """Only connection failures may leave a development challenge pending."""


# ==================== TOTP 绑定、解绑与状态 ====================

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
    data = request.get_json() or {}
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


# ==================== 设备绑定与解绑 ====================

@mfa_bp.route('/mfa/bind/device', methods=['POST'])
@jwt_required()
def bind_device():
    """绑定设备（存储设备ID和公钥）"""
    data = request.get_json() or {}
    device_id = data.get('device_id')
    if not isinstance(device_id, str) or not device_id or len(device_id) > 50:
        return jsonify(msg='Valid device_id is required'), 400
    device_pubkey = data.get('device_pubkey')  # 设备公钥（可选）

    username = get_jwt_identity()
    user = User.query.filter_by(username=username).first()

    # 检查设备是否已绑定
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
    device_id = data.get('device_id')
    if not device_id:
        return jsonify({"msg": "device_id is required"}), 400

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
    AuthSession.query.filter_by(user_id=user.id, device_id=device_id).update(
        {AuthSession.status: 'failed'}, synchronize_session=False)
    UnlockToken.query.filter_by(user_id=user.id, device_id=device_id).update(
        {UnlockToken.is_used: True}, synchronize_session=False)
    GuestPass.query.filter_by(created_by=user.id, device_id=device_id).update(
        {GuestPass.is_active: False}, synchronize_session=False)
    db.session.commit()

    return jsonify({"msg": "Device unbound successfully"}), 200


# ==================== 开门认证流程 (含防爆破) ====================

@mfa_bp.route('/mfa/open-door/request', methods=['POST'])
@jwt_required()
def open_door_request():
    """发起开门请求（拦截已锁定设备）"""
    data = request.get_json() or {}
    device_id = data.get('device_id')
    if not isinstance(device_id, str) or not device_id or len(device_id) > 50:
        return jsonify(msg='Valid device_id is required'), 400

    username = get_jwt_identity()
    user = User.query.filter_by(username=username).first()

    # 验证设备绑定
    device_bound = device_binding(user.id, device_id)
    if not device_bound:
        return jsonify({"msg": "Device not bound"}), 403

    # ================= 新增：设备锁定状态拦截 =================
    if getattr(device_bound, 'is_locked', False):
        log = AccessLog(action='BLOCKED_LOCKED_DEVICE_ATTEMPT', username=username)
        db.session.add(log)
        db.session.commit()
        return jsonify({
            "msg": "Device is LOCKED due to multiple failed attempts. Please contact Administrator.",
            "code": "DEVICE_LOCKED"
        }), 423
    # ========================================================

    # 创建认证会话
    request_id = secrets.token_hex(32)
    nonce = secrets.token_hex(32)

    required_factors = evaluate_mfa_policy(user.id)
    session = AuthSession(
        request_id=request_id,
        user_id=user.id,
        nonce=nonce,
        device_id=device_id,
        requires_totp='totp' in required_factors,
        status='pending',
        device_verified=True,  # 设备已验证
        expires_at=datetime.now() + timedelta(minutes=5)
    )
    db.session.add(session)
    db.session.commit()

    # 评估当前场景需要哪些认证因子
    required_factors = evaluate_mfa_policy(user.id)

    device_dispatch = None
    if 'face' in required_factors:
        try:
            device_dispatch = _dispatch_face_challenge(device_id, request_id, nonce)
        except DeviceUnavailable as exc:
            if not current_app.config['DEVICE_DISPATCH_REQUIRED']:
                # No synthetic face success: a simulator must submit an authenticated v2 result.
                return jsonify(msg='Auth session pending encrypted face result', request_id=request_id,
                               nonce=nonce, requires_face=True, requires_totp=session.requires_totp,
                               device_dispatch={'status': 'pending', 'detail': str(exc)}), 200
            session.status = 'failed'
            db.session.commit()
            return jsonify(msg=str(exc), code='DEVICE_DISPATCH_FAILED'), 502
        except RuntimeError as exc:
            session.status = 'failed'
            db.session.add(FaceRecognitionLog(
                request_id=request_id,
                device_id=device_id,
                expected_username=user.username,
                face_user_id=None,
                similarity_score=0.0,
                passed=False,
                failure_reason=f'device_dispatch_failed: {exc}',
            ))
            db.session.commit()
            return jsonify({
                "msg": str(exc),
                "code": "DEVICE_DISPATCH_FAILED"
            }), 502

    return jsonify({
        "msg": "Auth session created",
        "request_id": request_id,
        "nonce": nonce,
        "requires_face": 'face' in required_factors,
        "requires_totp": 'totp' in required_factors,
        "device_dispatch": device_dispatch
    }), 200


@mfa_bp.route('/mfa/open-door/face-result', methods=['POST'])
def receive_face_result():
    """接收树莓派上传的人脸识别结果。必须使用 v2 加密信封（PAKE + AES-CBC + HMAC）。"""
    raw = request.get_json() or {}

    # 强制要求 v2 加密信封：拒绝明文与旧版 ECC 兼容包
    if not isinstance(raw.get('header'), dict) or raw['header'].get('version') != PROTOCOL_VERSION:
        return jsonify({"msg": "Encrypted v2 payload required"}), 401

    try:
        data = decrypt_secure_payload(raw)
    except Exception as exc:
        return jsonify({"msg": "Invalid encrypted payload", "detail": str(exc)}), 400

    request_id = data.get('request_id')
    face_user_id = data.get('face_user_id')
    if face_user_id is not None and not isinstance(face_user_id, str):
        return jsonify(msg='face_user_id must be a string or null'), 400
    similarity_score = data.get('similarity_score')
    device_id = data.get('device_id')
    session_nonce = data.get('session_nonce')
    snapshot_path = data.get('snapshot')

    # 查找认证会话
    session = AuthSession.query.filter_by(request_id=request_id).first()
    if not session:
        return jsonify({"msg": "Invalid request_id"}), 404

    if session.status != 'pending':
        return jsonify({"msg": "Session already processed"}), 400
    if not session.expires_at or session.expires_at <= datetime.now():
        return jsonify(msg='Authentication session expired'), 410
    if not session.device_id or session.device_id != device_id:
        return jsonify(msg='Device does not match authentication session'), 403
    user = db.session.get(User, session.user_id)
    binding = device_binding(session.user_id, device_id)
    if not user or user.status != 'approved' or not binding or binding.is_locked:
        return jsonify(msg='Device or account authorization revoked'), 403
    if (not isinstance(similarity_score, (int, float)) or isinstance(similarity_score, bool)
            or not math.isfinite(similarity_score) or not -1 <= similarity_score <= 1):
        return jsonify(msg='Invalid similarity_score'), 400
    claimed = AuthSession.query.filter(
        AuthSession.id == session.id, AuthSession.status == 'pending',
        AuthSession.expires_at > datetime.now(),
    ).update({AuthSession.status: 'processing'}, synchronize_session=False)
    if not claimed:
        db.session.rollback()
        return jsonify(msg='Session already processed or expired'), 409

    # 校验 nonce：Pi 必须回传 open-door/request 阶段签发的 session.nonce
    if not session_nonce or session_nonce != session.nonce:
        session.status = 'failed'
        db.session.add(FaceRecognitionLog(
            request_id=request_id,
            device_id=device_id,
            expected_username=user.username,
            face_user_id=face_user_id,
            similarity_score=similarity_score,
            passed=False,
            failure_reason='session_nonce_mismatch',
        ))
        record_failure(user.id, device_id)
        db.session.commit()
        return jsonify({"msg": "Session nonce mismatch"}), 401

    # 验证人脸结果
    normalized_face_user_id = _normalize_face_user_id(face_user_id)
    # Project threshold; accuracy and spoof resistance require independent evaluation.
    FACE_MATCH_THRESHOLD = 0.90
    passed = (
        normalized_face_user_id == user.username
        and similarity_score is not None
        and similarity_score >= FACE_MATCH_THRESHOLD
    )
    if not snapshot_path and data.get('snapshot_image'):
        snapshot_path = save_snapshot_image(data.get('snapshot_image'), prefix='face')
    db.session.add(FaceRecognitionLog(
        request_id=request_id,
        device_id=device_id,
        expected_username=user.username if user else None,
        face_user_id=face_user_id,
        similarity_score=similarity_score,
        passed=passed,
        snapshot_path=snapshot_path,
        failure_reason=None if passed else 'face_user_or_score_mismatch',
    ))

    if passed:
        session.face_verified = True
        session.face_user_id = normalized_face_user_id
        session.similarity_score = similarity_score
        session.status = 'face_verified'
        db.session.commit()

        return jsonify({
            "msg": "Face verified",
            "requires_totp": session.requires_totp,
            "snapshot": snapshot_path,
            "snapshot_url": snapshot_path,
        }), 200
    else:
        session.status = 'failed'
        # ================= 新增：人脸验证失败，增加失败计数 =================
        record_failure(user.id, device_id)
        db.session.commit()
        # ==============================================================
        return jsonify({
            "msg": "Face verification failed",
            "snapshot": snapshot_path,
            "snapshot_url": snapshot_path,
        }), 401


@mfa_bp.route('/mfa/open-door/confirm', methods=['POST'])
@jwt_required()
def open_door_confirm():
    """确认开门（汇总所有因子，签发开门令牌）"""
    data = request.get_json() or {}
    request_id = data.get('request_id')
    totp_code = data.get('totp_code')  # 如果需要TOTP

    username = get_jwt_identity()
    user = User.query.filter_by(username=username).first()

    # 查找认证会话
    session = AuthSession.query.filter_by(request_id=request_id, user_id=user.id).first()
    if not session:
        return jsonify({"msg": "Invalid session"}), 404

    if not session.expires_at or session.expires_at <= datetime.now():
        return jsonify(msg='Authentication session expired'), 410
    if session.status == 'completed':
        return jsonify(msg='Authentication session already completed'), 409
    binding = device_binding(user.id, session.device_id)
    if not binding or binding.is_locked:
        return jsonify(msg='Device authorization revoked or locked'), 403

    if session.status == 'failed':
        return jsonify({"msg": "Authentication failed"}), 401

    # Use the policy fixed when the challenge was created, including across clock boundaries.
    required_factors = ['device', 'face']
    if session.requires_totp:
        required_factors.append('totp')

    # 1. 核验生物因子 (人脸)
    if 'face' in required_factors and not session.face_verified:
        return jsonify({"msg": "Face verification missing"}), 401

    # 2. 核验基础持有因子 (设备)
    if 'device' in required_factors and not session.device_verified:
        return jsonify({"msg": "Device verification missing"}), 401

    # 3. 检查是否需要TOTP
    if 'totp' in required_factors:
        if not totp_code:
            return jsonify({"msg": "Night mode: TOTP code required"}), 400

        # 验证TOTP
        credential = MFACredential.query.filter_by(
            user_id=user.id,
            credential_type='totp',
            is_active=True
        ).first()
        if not credential:
            return jsonify(msg='TOTP credential no longer active'), 403
        totp = pyotp.TOTP(credential.credential_data)
        if not totp.verify(totp_code, valid_window=1):
            claimed = AuthSession.query.filter_by(id=session.id, status='face_verified').update(
                {AuthSession.status: 'failed'}, synchronize_session=False)
            # ================= 新增：TOTP验证失败，增加失败计数 =================
            if claimed:
                record_failure(user.id, session.device_id)
            db.session.commit()
            # ================================================================
            return jsonify({"msg": "Invalid TOTP code"}), 401

        session.totp_verified = True

    # ================= 新增：所有安全因子验证成功，重置失败计数 =================
    claimed = AuthSession.query.filter(
        AuthSession.id == session.id, AuthSession.status == 'face_verified',
        AuthSession.expires_at > datetime.now(),
    ).update({AuthSession.status: 'completed'}, synchronize_session=False)
    if not claimed:
        db.session.rollback()
        return jsonify(msg='Authentication session already processed or expired'), 409
    reset_failures(user.id, session.device_id)
    # =========================================================================

    # 所有因子验证通过，签发开门令牌
    token = secrets.token_urlsafe(64)
    unlock_token = UnlockToken(
        token=token,
        user_id=user.id,
        request_id=request_id,
        device_id=session.device_id,
        expires_at=datetime.now() + timedelta(seconds=60)
    )
    db.session.add(unlock_token)

    # 记录访问日志
    log = AccessLog(action='UNLOCK_TOKEN_ISSUED', username=username)
    db.session.add(log)
    db.session.commit()

    return jsonify({
        "msg": "Authentication successful",
        "unlock_token": token,
        "device_id": session.device_id,
        "expires_in": 60
    }), 200


# ==================== 管理员设备解锁 ====================

@mfa_bp.route('/mfa/admin/device/unlock', methods=['POST'])
@jwt_required()
def admin_unlock_device():
    """管理员介入：解除特定用户的设备锁定"""
    admin_name = get_jwt_identity()
    admin_user = User.query.filter_by(username=admin_name).first()
    if not admin_user or admin_user.role != 'admin':
        return jsonify({"msg": "Admin privilege required"}), 403

    data = request.get_json()
    target_username = data.get('target_username')

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
    db.session.commit()

    log = AccessLog(action=f'ADMIN_UNLOCK_DEVICE_FOR_{target_username}', username=admin_name)
    db.session.add(log)
    db.session.commit()

    return jsonify({"msg": f"Device for {target_username} has been successfully unlocked."}), 200
# ==================== 访客授权 ====================

@mfa_bp.route('/mfa/guest/create', methods=['POST'])
@jwt_required()
def create_guest_pass():
    """创建访客临时授权"""
    data = request.get_json() or {}
    device_id = data.get('device_id')
    guest_name = data.get('guest_name')
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
    log = AccessLog(action='GUEST_TOKEN_ISSUED', username=guest_pass.guest_name or 'Guest')
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

    guest_pass.is_active = False
    db.session.commit()

    return jsonify({"msg": "Guest pass revoked"}), 200


# ==================== 辅助函数 (防爆破与策略引擎) ====================

def evaluate_mfa_policy(user_id):
    """
    场景因子评估：动态决定当前请求需要哪些验证因子。
    返回包含所需因子标识符的列表，例: ['device', 'face', 'totp']
    """
    required_factors = ['device', 'face']
    current_hour = datetime.now().hour
    is_deep_night = current_hour >= 22 or current_hour < 6

    if is_deep_night:
        required_factors.append('totp')

    return required_factors


def _resolve_device_service_base(device_id):
    env_key = f"SMART_LOCK_DEVICE_URL_{device_id.upper()}"
    override = os.environ.get(env_key)
    if override:
        return override.rstrip('/')
    global_override = os.environ.get("SMART_LOCK_DEVICE_URL")
    if global_override:
        return global_override.rstrip('/')

    device = Device.query.filter_by(device_id=device_id).first()
    if not device or not device.ip_address:
        return (
            f"{current_app.config['DEVICE_SERVICE_SCHEME']}://"
            f"localhost:{current_app.config['DEVICE_SERVICE_PORT']}"
        )

    raw = device.ip_address.strip()
    if raw.startswith('http://') or raw.startswith('https://'):
        return raw.rstrip('/')
    if ':' in raw and raw.count(':') == 1:
        return f"{current_app.config['DEVICE_SERVICE_SCHEME']}://{raw}"
    return (
        f"{current_app.config['DEVICE_SERVICE_SCHEME']}://"
        f"{raw}:{current_app.config['DEVICE_SERVICE_PORT']}"
    )


def _dispatch_face_challenge(device_id, request_id, nonce):
    base_url = _resolve_device_service_base(device_id)
    try:
        response = requests.post(
            f"{base_url}/auth_challenge",
            json={"request_id": request_id, "nonce": nonce},
            timeout=current_app.config['DEVICE_SERVICE_TIMEOUT'],
        )
    except (requests.ConnectionError, requests.Timeout) as exc:
        raise DeviceUnavailable(f"Failed to reach device service for {device_id}: {exc}") from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"Device dispatch failed for {device_id}: {exc}") from exc

    # 网关（树莓派）返回非 2xx 时，把它 JSON 里的 message/detail 抽出来一起抛，
    # 前端拿到的 502 才有根因，而不是只有一个 "500 Server Error"。
    if response.status_code >= 400:
        detail = None
        try:
            body = response.json()
            detail = body.get('detail') or body.get('message') or body.get('msg')
            backend_reply = body.get('backend_reply') or {}
            if not detail:
                detail = backend_reply.get('msg') or backend_reply.get('detail')
        except ValueError:
            detail = (response.text or '').strip()[:300]
        raise RuntimeError(
            f"Device {device_id} returned HTTP {response.status_code}: {detail or 'no detail from device'}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"Device {device_id} returned invalid JSON") from exc

    backend_reply = payload.get('backend_reply') or {}
    if payload.get('status') == 'error':
        raise RuntimeError(payload.get('message') or f"Device {device_id} reported an error")
    if backend_reply.get('msg') == 'Face verification failed':
        raise RuntimeError(f"Device {device_id} completed recognition but face verification failed")

    return {
        "device_url": base_url,
        "frame_source": payload.get('frame_source'),
        "recognition": payload.get('recognition'),
        "backend_reply": backend_reply,
        "snapshot": backend_reply.get('snapshot') or backend_reply.get('snapshot_url'),
    }


def _normalize_face_user_id(face_user_id):
    if not face_user_id:
        return face_user_id

    raw_mapping = os.environ.get("SMART_LOCK_FACE_ID_MAP", "").strip()
    if not raw_mapping:
        return face_user_id

    mapping = {}
    for pair in raw_mapping.split(','):
        pair = pair.strip()
        if not pair or '=' not in pair:
            continue
        source, target = pair.split('=', 1)
        source = source.strip()
        target = target.strip()
        if source and target:
            mapping[source] = target

    return mapping.get(face_user_id, face_user_id)
