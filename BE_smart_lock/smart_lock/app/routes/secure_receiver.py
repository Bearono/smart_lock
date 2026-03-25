import base64
import json
from flask import Blueprint, request, jsonify
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

from .AesCBCalgorithm import AesDecrypt
from .ECCalgorithm import decrypt_aes_key_ecc
# 导入原本 video.py 里的共享变量，这样解密后的图能直接在网页显示
from app import utils

secure_bp = Blueprint('secure', __name__)

# 加载私钥（确保文件在根目录）
with open("./backend_priv.pem", "rb") as f:
    PRIVATE_KEY = serialization.load_pem_private_key(
        f.read(), password=None, backend=default_backend()
    )


@secure_bp.route('/api/secure/upload', methods=['POST'])
def handle_rpi_data():
    data = request.get_json()

    try:
        # 1. 解密密钥：用 ECC 私钥解开 enc_key 得到 AES_KEY
        enc_key_bytes = base64.b64decode(data['enc_key'])
        aes_key_bytes = decrypt_aes_key_ecc(enc_key_bytes, PRIVATE_KEY)

        # 2. 解密数据：用 AES_KEY 解开 payload 得到原始 JSON
        aes_key_str = aes_key_bytes.decode('utf-8')
        decrypted_json_bytes = AesDecrypt(data['payload'], aes_key_str)
        business_data = json.loads(decrypted_json_bytes.decode('utf-8'))

        # 3. 业务对接：如果是图片数据，直接同步到 video 监控页面
        if 'image' in business_data:
            image_bytes = base64.b64decode(business_data['image'])
            # 【关键对接点】直接修改 utils 里的全局变量，前端页面就会变
            utils.global_frame_bytes = image_bytes
            print(">>> [安全模块] 成功解密并更新了一帧实时画面")

        return jsonify({"status": "success", "msg": "数据已安全送达并解密"}), 200

    except Exception as e:
        print(f"解密失败: {e}")
        return jsonify({"status": "error", "msg": "解密失败，请检查密钥"}), 400