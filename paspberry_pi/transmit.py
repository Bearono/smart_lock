import requests
import json
import time
import base64
import cv2
from AesCBCalgorithm import AesEncrypt, genKey
from ECCalgorithm import encrypt_aes_key_ecc
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

class NetworkTransmitter:
    def __init__(self, remote_url, device_id="RPI_LOCK_01"):
        self.remote_url = remote_url
        self.device_id = device_id
        # 加载后端公钥（用于 ECC 加密 AES 密钥）
        try:
            with open("backend_pub.pem", "rb") as f:
                self.backend_pub_key = serialization.load_pem_public_key(
                    f.read(), backend=default_backend()
                )
        except Exception as e:
            print(f"致命错误：公钥加载失败，请检查文件是否存在: {e}")
            self.backend_pub_key = None

    def _send_encrypted(self, endpoint, data_dict):
        """核心加密发送方法: AES加密数据 + ECC加密密钥"""
        if not self.backend_pub_key:
            return {"status": "error", "msg": "No public key"}

        # 1. 生成临时 AES 密钥 (16位)
        aes_key = genKey() 
        # 2. AES 加密业务数据 (Payload)
        payload = AesEncrypt(json.dumps(data_dict), aes_key)
        # 3. ECC 加密 AES 密钥
        encrypted_key_blob = encrypt_aes_key_ecc(aes_key.encode(), self.backend_pub_key)
        
        # 打包安全报文
        secure_packet = {
            "device_id": self.device_id,
            "payload": payload,
            "enc_key": base64.b64encode(encrypted_key_blob).decode()
        }
        
        try:
            res = requests.post(f"{self.remote_url}{endpoint}", json=secure_packet, timeout=10)
            return res.json()
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    def send_recognition_result(self, user_id, confidence):
        """发送人脸/指纹识别结果 (修复补全)"""
        data = {
            "type": "recognition",
            "user_id": user_id,
            "confidence": confidence,
            "timestamp": int(time.time())
        }
        # 发送到后端接收接口
        return self._send_encrypted("/api/secure/upload", data)

    def upload_image(self, frame):
        """发送图片数据"""
        _, buffer = cv2.imencode('.jpg', frame)
        img_base64 = base64.b64encode(buffer).decode('utf-8')
        
        data = {
            "type": "image_upload",
            "image": img_base64,
            "timestamp": int(time.time())
        }
        return self._send_encrypted("/api/secure/upload", data)