"""Door HTTP endpoints; registered on the shared MFA blueprint."""

import math
from flask import request, jsonify, current_app
from app.extensions import db
from app.door_auth import device_binding, record_failure, reset_failures
from app.validation import text_field, totp_code as validate_totp_code
from app.models import AccessLog, AuthSession, FaceRecognitionLog, MFACredential, UnlockToken, User
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timedelta
import secrets
from app.media_ingest import save_snapshot_image
from app.secure_payload import decrypt_secure_payload
from app.authenticators import consume_totp
from app.face_challenges import DeviceUnavailable, dispatch_face_challenge, normalize_face_user_id
from app.door_auth import evaluate_mfa_policy
from . import mfa_bp


@mfa_bp.route("/mfa/open-door/request", methods=["POST"])
@jwt_required()
def open_door_request():
    """发起开门请求（拦截已锁定设备）"""
    data = request.get_json() or {}
    device_id = data.get("device_id")
    if not isinstance(device_id, str) or not device_id or len(device_id) > 50:
        return jsonify(msg="Valid device_id is required"), 400

    username = get_jwt_identity()
    user = User.query.filter_by(username=username).first()

    # 验证设备绑定
    device_bound = device_binding(user.id, device_id)
    if not device_bound:
        return jsonify({"msg": "Device not bound"}), 403

    # ================= 新增：设备锁定状态拦截 =================
    if getattr(device_bound, "is_locked", False):
        log = AccessLog(
            action="BLOCKED_LOCKED_DEVICE_ATTEMPT", username=username, device_id=device_id
        )
        db.session.add(log)
        db.session.commit()
        return jsonify(
            {
                "msg": "Device is LOCKED due to multiple failed attempts. Please contact Administrator.",
                "code": "DEVICE_LOCKED",
            }
        ), 423
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
        requires_totp="totp" in required_factors,
        status="pending",
        device_verified=True,  # 设备已验证
        expires_at=datetime.now() + timedelta(minutes=5),
    )
    db.session.add(session)
    db.session.commit()

    # 评估当前场景需要哪些认证因子
    required_factors = evaluate_mfa_policy(user.id)

    device_dispatch = None
    if "face" in required_factors:
        try:
            device_dispatch = dispatch_face_challenge(device_id, request_id, nonce)
        except DeviceUnavailable as exc:
            if not current_app.config["DEVICE_DISPATCH_REQUIRED"]:
                # No synthetic face success: a simulator must submit an authenticated v2 result.
                return jsonify(
                    msg="Auth session pending encrypted face result",
                    request_id=request_id,
                    nonce=nonce,
                    requires_face=True,
                    requires_totp=session.requires_totp,
                    device_dispatch={"status": "pending", "detail": str(exc)},
                ), 200
            session.status = "failed"
            db.session.commit()
            return jsonify(msg=str(exc), code="DEVICE_DISPATCH_FAILED"), 502
        except RuntimeError as exc:
            # The device forwards our callback's rejection. Use the authenticated,
            # persisted evidence rather than misclassifying it as a gateway outage.
            db.session.refresh(session)
            evidence = (
                FaceRecognitionLog.query.filter_by(
                    request_id=request_id,
                    device_id=device_id,
                    passed=False,
                )
                .order_by(FaceRecognitionLog.id.desc())
                .first()
            )
            if (
                session.status == "failed"
                and evidence
                and evidence.failure_reason
                in ("face_user_or_score_mismatch", "face_presentation_check_failed")
            ):
                reason = evidence.failure_reason
                if not evidence.face_user_id and evidence.similarity_score == 0:
                    reason = "face_not_identified"
                return jsonify(
                    msg="Face verification failed",
                    code="FACE_VERIFICATION_FAILED",
                    reason=reason,
                    snapshot=evidence.snapshot_path,
                ), 401
            session.status = "failed"
            db.session.add(
                FaceRecognitionLog(
                    request_id=request_id,
                    device_id=device_id,
                    expected_username=user.username,
                    face_user_id=None,
                    similarity_score=0.0,
                    passed=False,
                    failure_reason=f"device_dispatch_failed: {exc}",
                )
            )
            db.session.commit()
            return jsonify({"msg": str(exc), "code": "DEVICE_DISPATCH_FAILED"}), 502

    return jsonify(
        {
            "msg": "Auth session created",
            "request_id": request_id,
            "nonce": nonce,
            "requires_face": "face" in required_factors,
            "requires_totp": "totp" in required_factors,
            "device_dispatch": device_dispatch,
        }
    ), 200


@mfa_bp.route("/mfa/open-door/face-result", methods=["POST"])
def receive_face_result():
    """Receive device-authenticated face evidence through the secure envelope."""
    raw = request.get_json() or {}

    data = decrypt_secure_payload(raw)

    request_id = text_field(data, "request_id", maximum=64)
    face_user_id = data.get("face_user_id")
    if face_user_id is not None and not isinstance(face_user_id, str):
        return jsonify(msg="face_user_id must be a string or null"), 400
    similarity_score = data.get("similarity_score")
    pad_score = data.get("liveness_score")
    if pad_score is not None and (
        isinstance(pad_score, bool)
        or not isinstance(pad_score, (int, float))
        or not math.isfinite(pad_score)
        or not 0 <= pad_score <= 1
    ):
        return jsonify(msg="Invalid presentation attack score"), 400
    device_id = data.get("device_id")
    session_nonce = data.get("session_nonce")
    # Never accept device-supplied URLs or another device's asset as evidence.
    snapshot_path = None

    # 查找认证会话
    session = AuthSession.query.filter_by(request_id=request_id).first()
    if not session:
        return jsonify({"msg": "Invalid request_id"}), 404

    if session.status != "pending":
        return jsonify({"msg": "Session already processed"}), 400
    if not session.expires_at or session.expires_at <= datetime.now():
        return jsonify(msg="Authentication session expired"), 410
    if not session.device_id or session.device_id != device_id:
        return jsonify(msg="Device does not match authentication session"), 403
    user = db.session.get(User, session.user_id)
    binding = device_binding(session.user_id, device_id)
    if not user or user.status != "approved" or not binding or binding.is_locked:
        return jsonify(msg="Device or account authorization revoked"), 403
    if (
        not isinstance(similarity_score, (int, float))
        or isinstance(similarity_score, bool)
        or not math.isfinite(similarity_score)
        or not -1 <= similarity_score <= 1
    ):
        return jsonify(msg="Invalid similarity_score"), 400
    claimed = AuthSession.query.filter(
        AuthSession.id == session.id,
        AuthSession.status == "pending",
        AuthSession.expires_at > datetime.now(),
    ).update({AuthSession.status: "processing"}, synchronize_session=False)
    if not claimed:
        db.session.rollback()
        return jsonify(msg="Session already processed or expired"), 409

    # 校验 nonce：Pi 必须回传 open-door/request 阶段签发的 session.nonce
    if not session_nonce or session_nonce != session.nonce:
        session.status = "failed"
        db.session.add(
            FaceRecognitionLog(
                request_id=request_id,
                device_id=device_id,
                expected_username=user.username,
                face_user_id=face_user_id,
                similarity_score=similarity_score,
                passed=False,
                failure_reason="session_nonce_mismatch",
            )
        )
        record_failure(user.id, device_id)
        db.session.commit()
        return jsonify({"msg": "Session nonce mismatch"}), 401

    # 验证人脸结果
    normalized_face_user_id = normalize_face_user_id(face_user_id)
    # Project threshold; accuracy and spoof resistance require independent evaluation.
    FACE_MATCH_THRESHOLD = 0.90
    passed = (
        normalized_face_user_id == user.username
        and similarity_score is not None
        and similarity_score >= FACE_MATCH_THRESHOLD
    )
    identity_passed = passed
    # Conservative initial operating point; independent local PAD validation is required.
    if current_app.config["FACE_PAD_REQUIRED"]:
        passed = passed and pad_score is not None and pad_score >= 0.80
    if not snapshot_path and data.get("snapshot_image"):
        try:
            snapshot_path = save_snapshot_image(
                data.get("snapshot_image"), prefix="face", device_id=device_id
            )
        except (ValueError, TypeError):
            return jsonify(msg="Invalid snapshot image"), 400
    db.session.add(
        FaceRecognitionLog(
            request_id=request_id,
            device_id=device_id,
            expected_username=user.username if user else None,
            face_user_id=face_user_id,
            similarity_score=similarity_score,
            liveness_score=pad_score,
            passed=passed,
            snapshot_path=snapshot_path,
            failure_reason=(
                None
                if passed
                else "face_presentation_check_failed"
                if identity_passed
                else "face_user_or_score_mismatch"
            ),
        )
    )

    if passed:
        session.face_verified = True
        session.face_user_id = normalized_face_user_id
        session.similarity_score = similarity_score
        session.status = "face_verified"
        db.session.commit()

        return jsonify(
            {
                "msg": "Face verified",
                "requires_totp": session.requires_totp,
                "snapshot": snapshot_path,
                "snapshot_url": snapshot_path,
            }
        ), 200
    else:
        session.status = "failed"
        # ================= 新增：人脸验证失败，增加失败计数 =================
        record_failure(user.id, device_id)
        db.session.commit()
        # ==============================================================
        return jsonify(
            {
                "msg": "Face verification failed",
                "snapshot": snapshot_path,
                "snapshot_url": snapshot_path,
            }
        ), 401


@mfa_bp.route("/mfa/open-door/confirm", methods=["POST"])
@jwt_required()
def open_door_confirm():
    """确认开门（汇总所有因子，签发开门令牌）"""
    data = request.get_json() or {}
    request_id = text_field(data, "request_id", maximum=64)
    totp_code = data.get("totp_code")  # 如果需要TOTP

    username = get_jwt_identity()
    user = User.query.filter_by(username=username).first()

    # 查找认证会话
    session = AuthSession.query.filter_by(request_id=request_id, user_id=user.id).first()
    if not session:
        return jsonify({"msg": "Invalid session"}), 404

    if not session.expires_at or session.expires_at <= datetime.now():
        return jsonify(msg="Authentication session expired"), 410
    if session.status == "completed":
        return jsonify(msg="Authentication session already completed"), 409
    binding = device_binding(user.id, session.device_id)
    if not binding or binding.is_locked:
        return jsonify(msg="Device authorization revoked or locked"), 403

    if session.status == "failed":
        return jsonify({"msg": "Authentication failed"}), 401

    # Use the policy fixed when the challenge was created, including across clock boundaries.
    required_factors = ["device", "face"]
    if session.requires_totp:
        required_factors.append("totp")

    # 1. 核验生物因子 (人脸)
    if "face" in required_factors and not session.face_verified:
        return jsonify({"msg": "Face verification missing"}), 401

    # 2. 核验基础持有因子 (设备)
    if "device" in required_factors and not session.device_verified:
        return jsonify({"msg": "Device verification missing"}), 401

    # 3. 检查是否需要TOTP
    if "totp" in required_factors:
        if not totp_code:
            return jsonify({"msg": "TOTP code required"}), 400
        totp_code = validate_totp_code(data, "totp_code")

        # 验证TOTP
        credential = MFACredential.query.filter_by(
            user_id=user.id, credential_type="totp", is_active=True
        ).first()
        if not credential:
            return jsonify(msg="TOTP credential no longer active"), 403
        if not consume_totp(credential, totp_code):
            claimed = AuthSession.query.filter_by(id=session.id, status="face_verified").update(
                {AuthSession.status: "failed"}, synchronize_session=False
            )
            # ================= 新增：TOTP验证失败，增加失败计数 =================
            if claimed:
                record_failure(user.id, session.device_id)
            db.session.commit()
            # ================================================================
            return jsonify(msg="Invalid or already used TOTP code"), 401

        session.totp_verified = True

    # ================= 新增：所有安全因子验证成功，重置失败计数 =================
    claimed = AuthSession.query.filter(
        AuthSession.id == session.id,
        AuthSession.status == "face_verified",
        AuthSession.expires_at > datetime.now(),
    ).update({AuthSession.status: "completed"}, synchronize_session=False)
    if not claimed:
        db.session.rollback()
        return jsonify(msg="Authentication session already processed or expired"), 409
    reset_failures(user.id, session.device_id)
    # =========================================================================

    # 所有因子验证通过，签发开门令牌
    token = secrets.token_urlsafe(64)
    unlock_token = UnlockToken(
        token=token,
        user_id=user.id,
        request_id=request_id,
        device_id=session.device_id,
        expires_at=datetime.now() + timedelta(seconds=60),
    )
    db.session.add(unlock_token)

    # 记录访问日志
    log = AccessLog(action="UNLOCK_TOKEN_ISSUED", username=username, device_id=session.device_id)
    db.session.add(log)
    db.session.commit()

    return jsonify(
        {
            "msg": "Authentication successful",
            "unlock_token": token,
            "device_id": session.device_id,
            "expires_in": 60,
        }
    ), 200
