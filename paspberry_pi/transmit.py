import base64
import json
import time
from pathlib import Path

import cv2
import requests
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

from AesCBCalgorithm import AesEncrypt, genKey
from ECCalgorithm import encrypt_aes_key_ecc


class NetworkTransmitter:
    def __init__(self, remote_url, device_id="RPI_LOCK_01"):
        self.remote_url = remote_url.rstrip("/")
        self.device_id = device_id
        self.backend_pub_key = self._load_backend_public_key()

    def _load_backend_public_key(self):
        base_dir = Path(__file__).resolve().parent
        candidate_paths = [
            base_dir / "backend_pub.pem",
            base_dir / "cv" / "code" / "gateway" / "backend_pub.pem",
            base_dir / "cv" / "backend_pub.pem",
        ]
        load_errors = []

        for key_path in candidate_paths:
            if not key_path.is_file():
                continue
            try:
                with key_path.open("rb") as key_file:
                    return serialization.load_pem_public_key(
                        key_file.read(),
                        backend=default_backend(),
                    )
            except Exception as exc:
                load_errors.append(f"{key_path}: {exc}")

        if load_errors:
            print("加载后端公钥失败: " + " | ".join(load_errors))
        else:
            print("未找到可用的 backend_pub.pem，无法进行加密通信。")
        return None

    def _send_encrypted(self, endpoint, data_dict):
        if not self.backend_pub_key:
            return {"status": "error", "msg": "No public key"}

        aes_key = genKey()
        payload = AesEncrypt(json.dumps(data_dict), aes_key)
        encrypted_key_blob = encrypt_aes_key_ecc(aes_key.encode(), self.backend_pub_key)

        secure_packet = {
            "device_id": self.device_id,
            "payload": payload,
            "enc_key": base64.b64encode(encrypted_key_blob).decode(),
        }

        try:
            response = requests.post(
                f"{self.remote_url}{endpoint}",
                json=secure_packet,
                timeout=10,
            )
            response.raise_for_status()
            try:
                return response.json()
            except ValueError:
                return {"status": "success", "raw_response": response.text}
        except Exception as exc:
            return {"status": "error", "msg": str(exc)}

    def send_recognition_result(self, user_id, confidence):
        data = {
            "type": "recognition",
            "user_id": user_id,
            "confidence": confidence,
            "timestamp": int(time.time()),
        }
        return self._send_encrypted("/api/secure/upload", data)

    def upload_image(self, frame):
        success, buffer = cv2.imencode(".jpg", frame)
        if not success:
            return {"status": "error", "msg": "Failed to encode image"}

        img_base64 = base64.b64encode(buffer).decode("utf-8")
        data = {
            "type": "image_upload",
            "image": img_base64,
            "timestamp": int(time.time()),
        }
        return self._send_encrypted("/api/secure/upload", data)

    def send_auth_result(self, request_id, face_user_id, similarity_score, liveness_score=None):
        """发送人脸认证结果到后端MFA服务"""
        data = {
            "request_id": request_id,
            "device_id": self.device_id,
            "face_user_id": face_user_id,
            "similarity_score": similarity_score,
            "liveness_score": liveness_score or 0.0,
            "timestamp": int(time.time()),
        }
        return self._send_encrypted("/api/mfa/open-door/face-result", data)

    def request_unlock_token(self, request_id):
        """请求开门令牌（TOTP验证后）"""
        data = {
            "request_id": request_id,
            "device_id": self.device_id,
        }
        return self._send_encrypted("/api/mfa/open-door/confirm", data)

