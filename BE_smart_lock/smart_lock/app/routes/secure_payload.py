from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any, Dict, Set

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding, serialization
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .AesCBCalgorithm import AesDecrypt
from .ECCalgorithm import decrypt_aes_key_ecc
from .security_protocol import (
    MAX_CLOCK_SKEW_SECONDS,
    PROTOCOL_VERSION,
    SecureEnvelope,
    b64d,
    canonical_json,
    constant_time_equal,
    hmac_sha256,
)
from .security import SECURITY_SESSIONS, prune_sessions

PRIVATE_KEY_PATH = Path(__file__).resolve().parents[2] / "backend_priv.pem"
SEEN_REQUEST_IDS: Set[str] = set()
SEEN_NONCES: Set[str] = set()
MAX_REPLAY_CACHE = 10000


def load_private_key():
    with PRIVATE_KEY_PATH.open("rb") as key_file:
        return serialization.load_pem_private_key(
            key_file.read(),
            password=None,
            backend=default_backend(),
        )


PRIVATE_KEY = load_private_key()


def _remember(value_set: Set[str], value: str) -> None:
    if len(value_set) > MAX_REPLAY_CACHE:
        value_set.clear()
    value_set.add(value)


def _decrypt_v2(packet: Dict[str, Any]) -> Dict[str, Any]:
    header = packet.get("header") or {}
    if header.get("version") != PROTOCOL_VERSION:
        raise ValueError("Unsupported secure protocol version")

    session_id = header.get("session_id")
    device_id = header.get("device_id")
    timestamp = int(header.get("timestamp", 0) or 0)
    request_id = header.get("request_id")
    nonce = header.get("nonce")

    if not session_id or not device_id or not request_id or not nonce:
        raise ValueError("Missing header fields")
    if abs(int(time.time()) - timestamp) > MAX_CLOCK_SKEW_SECONDS:
        raise ValueError("Expired secure message")
    if request_id in SEEN_REQUEST_IDS or nonce in SEEN_NONCES:
        raise ValueError("Replay attack detected")

    prune_sessions()
    session = SECURITY_SESSIONS.get(session_id)
    if not session:
        raise ValueError("Unknown or expired security session")
    if session.device_id != device_id:
        raise ValueError("Device/session mismatch")

    enc_key, mac_key = SecureEnvelope._derive_keys(session.session_key)
    mac = b64d(packet.get("mac", ""))
    mac_input = {
        "header": header,
        "iv": packet.get("iv"),
        "ciphertext": packet.get("ciphertext"),
    }
    expected_mac = hmac_sha256(mac_key, canonical_json(mac_input))
    if not constant_time_equal(mac, expected_mac):
        raise ValueError("Invalid MAC; message may be tampered")

    iv = b64d(packet["iv"])
    ciphertext = b64d(packet["ciphertext"])
    decryptor = Cipher(algorithms.AES(enc_key), modes.CBC(iv)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    plaintext = unpadder.update(padded) + unpadder.finalize()

    _remember(SEEN_REQUEST_IDS, request_id)
    _remember(SEEN_NONCES, nonce)
    business = json.loads(plaintext.decode("utf-8"))
    business.setdefault("device_id", device_id)
    business.setdefault("request_id", request_id)
    business.setdefault("timestamp", timestamp)
    if header.get("unlock_token"):
        business["unlock_token"] = header.get("unlock_token")
    return business


def _decrypt_legacy(packet: Dict[str, Any]) -> Dict[str, Any]:
    enc_key = packet.get("enc_key")
    payload = packet.get("payload")
    if not enc_key or not payload:
        raise ValueError("Missing encrypted payload fields")

    enc_key_bytes = base64.b64decode(enc_key)
    aes_key = decrypt_aes_key_ecc(enc_key_bytes, PRIVATE_KEY)
    if not aes_key:
        raise ValueError("Failed to decrypt AES key")
    if isinstance(aes_key, bytes):
        aes_key = aes_key.decode("utf-8")

    decrypted_json_bytes = AesDecrypt(payload, aes_key)
    return json.loads(decrypted_json_bytes.decode("utf-8"))


def decrypt_secure_payload(packet: Dict[str, Any]) -> Dict[str, Any]:
    """兼容 v2 安全信封与原 ECC+AES 包格式。"""
    if packet.get("header", {}).get("version") == PROTOCOL_VERSION:
        return _decrypt_v2(packet)
    return _decrypt_legacy(packet)
