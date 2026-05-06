import os
import sys
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, jsonify

from camera_core import CameraManager
from transmit import NetworkTransmitter


BASE_DIR = Path(__file__).resolve().parent
CV_CODE_DIR = BASE_DIR / "cv" / "code"

if str(CV_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CV_CODE_DIR))

from recognize import recognize  # noqa: E402


def _read_image(image_path: Path):
    """Read images safely on Windows paths containing non-ASCII characters."""
    try:
        data = np.fromfile(str(image_path), dtype=np.uint8)
    except OSError:
        return None
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def _get_test_frame():
    """Use a local sample image when the camera is unavailable."""
    faces_dir = BASE_DIR / "cv" / "outputs" / "faces"
    if not faces_dir.is_dir():
        return None

    for image_path in sorted(faces_dir.glob("*")):
        if image_path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
            frame = _read_image(image_path)
            if frame is not None:
                return frame
    return None


app = Flask(__name__)

BACKEND_URL = os.getenv("BACKEND_URL", "http://192.168.255.131:8000")
transmitter = NetworkTransmitter(remote_url=BACKEND_URL)
camera = CameraManager()


@app.route("/")
def index():
    return "智能门锁树莓派网关正在运行中..."


@app.route("/recognition_and_send", methods=["POST"])
def trigger_recognition():
    frame = camera.capture_frame()
    frame_source = "camera"

    if frame is None:
        frame = _get_test_frame()
        frame_source = "test_image"

    if frame is None:
        return jsonify({"status": "error", "message": "无法获取图像帧"}), 500

    try:
        user_id, confidence = recognize(frame)
    except Exception as exc:
        return jsonify(
            {
                "status": "error",
                "message": "CV 识别执行失败",
                "detail": str(exc),
                "frame_source": frame_source,
            }
        ), 500

    backend_response = transmitter.send_recognition_result(user_id, confidence)
    status_code = 200 if backend_response.get("status") != "error" else 500
    return (
        jsonify(
            {
                "status": "success" if status_code == 200 else "error",
                "frame_source": frame_source,
                "recognition": {
                    "user_id": user_id,
                    "confidence": confidence,
                },
                "backend_reply": backend_response,
            }
        ),
        status_code,
    )


@app.route("/capture_and_send", methods=["POST"])
def upload_raw_image():
    frame = camera.capture_frame()
    if frame is None:
        return jsonify({"status": "error", "message": "无法获取图像帧"}), 500

    upload_result = transmitter.upload_image(frame)
    status_code = 200 if upload_result.get("status") != "error" else 500
    return (
        jsonify(
            {
                "status": "image_sent" if status_code == 200 else "error",
                "info": upload_result,
            }
        ),
        status_code,
    )


@app.route("/auth_challenge", methods=["POST"])
def handle_auth_challenge():
    """接收后端的认证挑战，执行人脸识别并上传结果"""
    data = request.get_json()
    request_id = data.get('request_id')
    nonce = data.get('nonce')

    if not request_id or not nonce:
        return jsonify({"status": "error", "message": "缺少request_id或nonce"}), 400

    # 采集图像
    frame = camera.capture_frame()
    frame_source = "camera"

    if frame is None:
        frame = _get_test_frame()
        frame_source = "test_image"

    if frame is None:
        return jsonify({"status": "error", "message": "无法获取图像帧"}), 500

    # 执行人脸识别
    try:
        user_id, confidence = recognize(frame)
    except Exception as exc:
        return jsonify({
            "status": "error",
            "message": "CV识别失败",
            "detail": str(exc)
        }), 500

    # 上传认证结果到后端
    auth_result = transmitter.send_auth_result(
        request_id=request_id,
        face_user_id=user_id,
        similarity_score=confidence,
        liveness_score=0.85  # 活体检测分数（暂时固定值，后续可接入真实活体检测）
    )

    return jsonify({
        "status": "success",
        "frame_source": frame_source,
        "recognition": {
            "user_id": user_id,
            "confidence": confidence
        },
        "backend_reply": auth_result
    }), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
