from __future__ import annotations

import os
import time
import uuid
from typing import Dict

from flask import Blueprint, jsonify, request
from spake2 import SPAKE2_B

from .security_protocol import (
    PROTOCOL_VERSION,
    SPAKE2_BACKEND_ID,
    SecuritySession,
    b64d,
    b64e,
    canonical_json,
    hmac_sha256,
    hkdf,
)

security_bp = Blueprint("security", __name__)

# 演示环境默认口令；生产环境必须通过环境变量或数据库为每台设备配置独立强口令。
DEFAULT_DEVICE_PASSWORD = os.getenv("SMART_LOCK_DEVICE_PASSWORD", "ChangeMe-Spake2-Device-Password")
SESSION_TTL_SECONDS = int(os.getenv("SMART_LOCK_SESSION_TTL", "300"))

# 简易内存会话表，课程演示足够；生产环境建议迁移到 Redis/数据库。
SECURITY_SESSIONS: Dict[str, SecuritySession] = {}


def get_device_password(device_id: str) -> str:
    # 可在此对接 MFACredential / Device 表，实现 device_id -> 设备口令查询。
    return os.getenv(f"SMART_LOCK_PASSWORD_{device_id}", DEFAULT_DEVICE_PASSWORD)


def prune_sessions() -> None:
    now = time.time()
    for sid in list(SECURITY_SESSIONS.keys()):
        if SECURITY_SESSIONS[sid].expires_at < now:
            SECURITY_SESSIONS.pop(sid, None)


@security_bp.route("/api/security/spake2/start", methods=["POST"])
def spake2_start():
    """设备发起标准 SPAKE2 握手，后端返回 SPAKE2_B 消息与 challenge。"""
    data = request.get_json() or {}
    device_id = data.get("device_id")
    client_msg_b64 = data.get("client_pub")
    client_nonce_b64 = data.get("client_nonce")
    timestamp = int(data.get("timestamp", 0) or 0)

    if data.get("version") != PROTOCOL_VERSION or not device_id or not client_msg_b64 or not client_nonce_b64:
        return jsonify({"msg": "Invalid SPAKE2 start message"}), 400
    if abs(int(time.time()) - timestamp) > 120:
        return jsonify({"msg": "SPAKE2 start message expired"}), 400

    try:
        client_msg = b64d(client_msg_b64)
        client_nonce = b64d(client_nonce_b64)
        password = get_device_password(device_id).encode("utf-8")
        spake2 = SPAKE2_B(password, idA=device_id.encode("utf-8"), idB=SPAKE2_BACKEND_ID)
        server_msg = spake2.start()
        spake2_key = spake2.finish(client_msg)
    except Exception as exc:
        return jsonify({"msg": "Invalid SPAKE2 message or nonce", "detail": str(exc)}), 400

    server_nonce = os.urandom(16)
    session_id = uuid.uuid4().hex
    expires_at = time.time() + SESSION_TTL_SECONDS

    session_key = hkdf(
        spake2_key,
        salt=client_nonce + server_nonce + device_id.encode("utf-8"),
        info=b"smart-lock-spake2-session",
        length=32,
    )
    challenge = hmac_sha256(
        session_key,
        canonical_json({
            "session_id": session_id,
            "device_id": device_id,
            "client_nonce": client_nonce_b64,
            "server_nonce": b64e(server_nonce),
        }),
    )

    prune_sessions()
    SECURITY_SESSIONS[session_id] = SecuritySession(session_id, device_id, session_key, expires_at)

    return jsonify({
        "version": PROTOCOL_VERSION,
        "session_id": session_id,
        # 字段名保留 server_pub 是为了兼容上一版接口；实际内容已改为 SPAKE2_B 消息。
        "server_pub": b64e(server_msg),
        "server_nonce": b64e(server_nonce),
        "challenge": b64e(challenge),
        "expires_at": expires_at,
    }), 200


@security_bp.route("/api/security/session/<session_id>", methods=["GET"])
def session_status(session_id):
    prune_sessions()
    session = SECURITY_SESSIONS.get(session_id)
    if not session:
        return jsonify({"active": False}), 404
    return jsonify({
        "active": True,
        "device_id": session.device_id,
        "expires_at": session.expires_at,
    }), 200
