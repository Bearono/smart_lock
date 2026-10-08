from __future__ import annotations

import os
import time
import uuid

from flask import Blueprint, jsonify, request, current_app
from spake2 import SPAKE2_B
from app.security_store import save_session, load_session, SecurePayloadError
from app.provisioning import device_password, validate_device_id
from smartlock_protocol.v3 import VERSION, transcript, derive_session_key, proof, verify_proof

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

def get_device_password(device_id: str) -> str:
    return device_password(device_id)


@security_bp.route("/api/security/spake2/start", methods=["POST"])
def spake2_start():
    """设备发起标准 SPAKE2 握手，后端返回 SPAKE2_B 消息与 challenge。"""
    data = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify(msg='Invalid SPAKE2 start message'), 400
    device_id = data.get("device_id")
    client_msg_b64 = data.get("client_pub")
    client_nonce_b64 = data.get("client_nonce")
    timestamp = data.get('timestamp')
    request_id = data.get('request_id')

    version = data.get('version')
    if (set(data) != {'version', 'device_id', 'client_pub', 'client_nonce', 'timestamp', 'request_id'}
            or version not in (PROTOCOL_VERSION, VERSION)
            or (version == PROTOCOL_VERSION and not current_app.config['ALLOW_PROTOCOL_V2'])
            or not validate_device_id(device_id)
            or not isinstance(request_id, str) or not 1 <= len(request_id) <= 64
            or type(timestamp) is not int):
        return jsonify({"msg": "Invalid SPAKE2 start message"}), 400
    if abs(int(time.time()) - timestamp) > 120:
        return jsonify({"msg": "SPAKE2 start message expired"}), 400

    password = get_device_password(device_id).encode('utf-8')
    try:
        client_msg = b64d(client_msg_b64)
        client_nonce = b64d(client_nonce_b64)
        if len(client_nonce) != 16 or len(client_msg) > 1024:
            raise ValueError('Invalid SPAKE2 nonce/message length')
        spake2 = SPAKE2_B(password, idA=device_id.encode("utf-8"), idB=SPAKE2_BACKEND_ID)
        server_msg = spake2.start()
        spake2_key = spake2.finish(client_msg)
    except Exception as exc:
        return jsonify({"msg": "Invalid SPAKE2 message or nonce", "detail": str(exc)}), 400

    server_nonce = os.urandom(16)
    session_id = uuid.uuid4().hex
    expires_at = time.time() + current_app.config['SECURITY_SESSION_TTL']

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

    reply = {
        "version": version,
        "session_id": session_id,
        # 字段名保留 server_pub 是为了兼容上一版接口；实际内容已改为 SPAKE2_B 消息。
        "server_pub": b64e(server_msg),
        "server_nonce": b64e(server_nonce),
        "challenge": b64e(challenge),
        "expires_at": expires_at,
    }
    if version == VERSION:
        context = transcript(data, reply)
        session_key = derive_session_key(session_key, context)
        reply['baseline_challenge'] = reply['challenge']
        reply['challenge'] = proof(session_key, context, 'server')
        save_session(SecuritySession(session_id, device_id, session_key, expires_at),
                     protocol_version=VERSION, confirmed=False, transcript=context)
    else:
        save_session(SecuritySession(session_id, device_id, session_key, expires_at))
    return jsonify(reply), 200


@security_bp.route('/api/security/spake2/confirm', methods=['POST'])
def spake2_confirm():
    from app import db
    from app.models import DeviceSecuritySession
    data = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify(msg='Invalid session confirmation'), 400
    session_id, candidate = data.get('session_id'), data.get('proof')
    if (not isinstance(session_id, str) or len(session_id) != 32
            or any(char not in '0123456789abcdef' for char in session_id)
            or not isinstance(candidate, str) or len(candidate) != 44):
        return jsonify(msg='Invalid session confirmation'), 400
    session = load_session(session_id, allow_pending=True)
    try:
        valid = (data.get('version') == VERSION and session.protocol_version == VERSION
                 and verify_proof(session.session_key, session.transcript_bytes, 'client', data.get('proof')))
    except (ValueError, TypeError):
        valid = False
    if not valid:
        return jsonify(msg='Invalid session confirmation'), 400
    DeviceSecuritySession.query.filter_by(id=session.session_id).update({'confirmed': True})
    db.session.commit()
    return jsonify(version=VERSION, proof=proof(session.session_key, session.transcript_bytes, 'confirmed')), 200


@security_bp.route("/api/security/session/<session_id>", methods=["GET"])
def session_status(session_id):
    try:
        session = load_session(session_id)
    except SecurePayloadError:
        return jsonify({"active": False}), 404
    return jsonify({
        "active": True,
        "device_id": session.device_id,
        "expires_at": session.expires_at,
    }), 200
