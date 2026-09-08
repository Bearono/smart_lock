import base64
import os
import time

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required

from app import utils
from .secure_payload import decrypt_secure_payload


secure_bp = Blueprint('secure', __name__)


def save_snapshot_image(image_b64, prefix="snapshot"):
    if not image_b64:
        return None

    image_bytes = base64.b64decode(image_b64)
    utils.global_frame_bytes = image_bytes

    save_dir = current_app.config['UPLOAD_FOLDER']
    os.makedirs(save_dir, exist_ok=True)
    filename = f"{prefix}_{int(time.time() * 1000)}.jpg"
    filepath = os.path.join(save_dir, filename)
    with open(filepath, "wb") as image_file:
        image_file.write(image_bytes)

    return f"/static/captures/{filename}"


@secure_bp.route('/api/snapshot/clear', methods=['POST'])
@jwt_required()
def clear_snapshot():
    """删除指定的快照文件；不带 filename 则清空当前实时帧。"""
    data = request.get_json() or {}
    snapshot_path = data.get('snapshot') or data.get('snapshot_url') or ''

    utils.global_frame_bytes = None

    if not snapshot_path:
        return jsonify({"msg": "Live frame cleared"}), 200

    prefix = '/static/captures/'
    if not snapshot_path.startswith(prefix):
        return jsonify({"msg": "Invalid snapshot path"}), 400

    filename = os.path.basename(snapshot_path[len(prefix):])
    if not filename or filename in ('.', '..'):
        return jsonify({"msg": "Invalid snapshot path"}), 400

    save_dir = current_app.config['UPLOAD_FOLDER']
    filepath = os.path.abspath(os.path.join(save_dir, filename))
    if not filepath.startswith(os.path.abspath(save_dir) + os.sep):
        return jsonify({"msg": "Invalid snapshot path"}), 400

    if os.path.isfile(filepath):
        try:
            os.remove(filepath)
        except OSError as exc:
            return jsonify({"msg": "Failed to remove file", "detail": str(exc)}), 500

    return jsonify({"msg": "Snapshot cleared"}), 200


@secure_bp.route('/api/secure/upload', methods=['POST'])
def handle_rpi_data():
    data = request.get_json()

    try:
        business_data = decrypt_secure_payload(data)

        if 'image' in business_data:
            snapshot_path = save_snapshot_image(business_data['image'], prefix="upload")
            return jsonify({
                "status": "success",
                "msg": "Data received securely",
                "snapshot": snapshot_path,
                "snapshot_url": snapshot_path,
            }), 200

        return jsonify({"status": "success", "msg": "Data received securely"}), 200

    except Exception as exc:
        print(f"Secure payload decrypt failed: {exc}")
        return jsonify({"status": "error", "msg": "Secure payload decrypt failed"}), 400
