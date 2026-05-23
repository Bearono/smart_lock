from flask import Blueprint, request, jsonify

from .secure_payload import decrypt_secure_payload
# 导入原本 video.py 里的共享变量，这样解密后的图能直接在网页显示
from app import utils

secure_bp = Blueprint('secure', __name__)


@secure_bp.route('/api/secure/upload', methods=['POST'])
def handle_rpi_data():
    data = request.get_json()

    try:
        business_data = decrypt_secure_payload(data)

        # 3. 业务对接：如果是图片数据，直接同步到 video 监控页面
        if 'image' in business_data:
            import base64

            image_bytes = base64.b64decode(business_data['image'])
            # 【关键对接点】直接修改 utils 里的全局变量，前端页面就会变
            utils.global_frame_bytes = image_bytes
            print(">>> [安全模块] 成功解密并更新了一帧实时画面")

        return jsonify({"status": "success", "msg": "数据已安全送达并解密"}), 200

    except Exception as e:
        print(f"解密失败: {e}")
        return jsonify({"status": "error", "msg": "解密失败，请检查密钥"}), 400
