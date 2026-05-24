"""
智能门锁安全通信协议 v2

目标：在原有 ECC + AES 框架上补齐标准 SPAKE2 口令认证握手、随机 nonce、
challenge、unlock_token、timestamp、request_id、device_id 与 MAC，降低篡改、
重放与伪造风险。

说明：本文件的握手阶段使用 python-spake2 库提供的 SPAKE2_A/SPAKE2_B 实现，
不再使用上一版的 X25519 + password hash 模拟流程。SPAKE2 只负责让硬件端与
后端基于共享设备口令协商出短期共享密钥；业务数据仍由 AES-CBC + HMAC-SHA256
安全信封负责保护。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from spake2 import SPAKE2_A

PROTOCOL_VERSION = "SL-SEC-v2"
MAX_CLOCK_SKEW_SECONDS = 120
SPAKE2_BACKEND_ID = b"smart-lock-backend"


def b64e(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def b64d(data: str) -> bytes:
    return base64.b64decode(data.encode("ascii"))


def canonical_json(data: Dict[str, Any]) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def password_fingerprint(password: str) -> bytes:
    return hashlib.sha256(password.encode("utf-8")).digest()


def hkdf(secret: bytes, *, salt: bytes, info: bytes, length: int = 32) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(secret)


def hmac_sha256(key: bytes, data: bytes) -> bytes:
    return hmac.new(key, data, hashlib.sha256).digest()


def constant_time_equal(a: bytes, b: bytes) -> bool:
    return hmac.compare_digest(a, b)


@dataclass
class Spake2ClientState:
    spake2: SPAKE2_A
    client_nonce: bytes
    device_id: str
    password: str


@dataclass
class SecuritySession:
    session_id: str
    device_id: str
    session_key: bytes
    expires_at: float


class Spake2Client:
    """设备侧标准 SPAKE2 客户端。"""

    def __init__(self, device_id: str, device_password: str):
        self.device_id = device_id
        self.device_password = device_password

    def begin(self) -> tuple[Spake2ClientState, Dict[str, str]]:
        client_nonce = os.urandom(16)
        spake2 = SPAKE2_A(
            self.device_password.encode("utf-8"),
            idA=self.device_id.encode("utf-8"),
            idB=SPAKE2_BACKEND_ID,
        )
        client_msg = spake2.start()
        state = Spake2ClientState(spake2, client_nonce, self.device_id, self.device_password)
        msg = {
            "version": PROTOCOL_VERSION,
            "device_id": self.device_id,
            # 字段名保留 client_pub 是为了兼容上一版接口；实际内容已改为 SPAKE2_A 消息。
            "client_pub": b64e(client_msg),
            "client_nonce": b64e(client_nonce),
            "timestamp": int(time.time()),
            "request_id": uuid.uuid4().hex,
        }
        return state, msg

    def finish(self, state: Spake2ClientState, server_msg: Dict[str, str]) -> SecuritySession:
        # 字段名保留 server_pub 是为了兼容上一版接口；实际内容已改为 SPAKE2_B 消息。
        spake2_key = state.spake2.finish(b64d(server_msg["server_pub"]))
        server_nonce = b64d(server_msg["server_nonce"])
        salt = state.client_nonce + server_nonce + state.device_id.encode("utf-8")
        session_key = hkdf(
            spake2_key,
            salt=salt,
            info=b"smart-lock-spake2-session",
            length=32,
        )
        expected_challenge = hmac_sha256(
            session_key,
            canonical_json({
                "session_id": server_msg["session_id"],
                "device_id": state.device_id,
                "client_nonce": b64e(state.client_nonce),
                "server_nonce": server_msg["server_nonce"],
            }),
        )
        if not constant_time_equal(expected_challenge, b64d(server_msg["challenge"])):
            raise ValueError("SPAKE2 challenge verification failed")
        return SecuritySession(
            session_id=server_msg["session_id"],
            device_id=state.device_id,
            session_key=session_key,
            expires_at=float(server_msg.get("expires_at", time.time() + 300)),
        )


class SecureEnvelope:
    """AES-CBC + HMAC-SHA256 的消息封装。"""

    @staticmethod
    def _derive_keys(session_key: bytes) -> tuple[bytes, bytes]:
        material = hkdf(session_key, salt=b"smart-lock-secure-envelope", info=b"aes-cbc+hmac", length=64)
        return material[:32], material[32:]

    @classmethod
    def seal(
        cls,
        session: SecuritySession,
        plaintext: Dict[str, Any],
        *,
        unlock_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = int(time.time())
        header = {
            "version": PROTOCOL_VERSION,
            "session_id": session.session_id,
            "device_id": session.device_id,
            "timestamp": now,
            "request_id": uuid.uuid4().hex,
            "nonce": b64e(os.urandom(16)),
        }
        if unlock_token:
            header["unlock_token"] = unlock_token

        enc_key, mac_key = cls._derive_keys(session.session_key)
        iv = os.urandom(16)
        padder = padding.PKCS7(128).padder()
        padded = padder.update(canonical_json(plaintext)) + padder.finalize()
        encryptor = Cipher(algorithms.AES(enc_key), modes.CBC(iv)).encryptor()
        ciphertext = encryptor.update(padded) + encryptor.finalize()

        body = {"header": header, "iv": b64e(iv), "ciphertext": b64e(ciphertext)}
        tag = hmac_sha256(mac_key, canonical_json(body))
        body["mac"] = b64e(tag)
        return body
