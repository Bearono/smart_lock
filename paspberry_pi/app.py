import os
import sys
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, jsonify, request

from camera_core import CameraManager
from transmit import NetworkTransmitter


BASE_DIR = Path(__file__).resolve().parent
CV_CODE_DIR = BASE_DIR / "cv" / "code"

if str(CV_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CV_CODE_DIR))

from recognize import recognize  # noqa: E402


def _read_image(image_path: Path):
    try:
        data = np.fromfile(str(image_path), dtype=np.uint8)
    except OSError:
        return None
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def _get_test_frame():
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

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
transmitter = NetworkTransmitter(remote_url=BACKEND_URL)
camera = CameraManager()


@app.route("/")
def index():
    return "Smart lock device service is running."


@app.route("/recognition_and_send", methods=["POST"])
def trigger_recognition():
    frame = camera.capture_frame()
    frame_source = "camera"

    if frame is None:
        frame = _get_test_frame()
        frame_source = "test_image"

    if frame is None:
        return jsonify({"status": "error", "message": "Unable to capture image frame"}), 500

    try:
        user_id, confidence = recognize(frame)
    except Exception as exc:
        return jsonify(
            {
                "status": "error",
                "message": "CV recognition failed",
                "detail": str(exc),
                "frame_source": frame_source,
            }
        ), 500

    backend_response = transmitter.send_recognition_result(user_id, confidence)
    backend_status = int(backend_response.get("http_status") or 200)
    status_code = backend_status if backend_status >= 400 else 200
    return (
        jsonify(
            {
                "status": "success" if status_code < 400 else "error",
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
        return jsonify({"status": "error", "message": "Unable to capture image frame"}), 500

    upload_result = transmitter.upload_image(frame)
    backend_status = int(upload_result.get("http_status") or 200)
    status_code = backend_status if backend_status >= 400 else 200
    return (
        jsonify(
            {
                "status": "image_sent" if status_code < 400 else "error",
                "info": upload_result,
            }
        ),
        status_code,
    )


@app.route("/auth_challenge", methods=["POST"])
def handle_auth_challenge():
    data = request.get_json() or {}
    request_id = data.get("request_id")
    nonce = data.get("nonce")

    if not request_id or not nonce:
        return jsonify({"status": "error", "message": "Missing request_id or nonce"}), 400

    frame = camera.capture_frame()
    frame_source = "camera"

    if frame is None:
        frame = _get_test_frame()
        frame_source = "test_image"

    if frame is None:
        return jsonify({"status": "error", "message": "Unable to capture image frame"}), 500

    try:
        user_id, confidence = recognize(frame)
    except Exception as exc:
        return jsonify(
            {
                "status": "error",
                "message": "CV recognition failed",
                "detail": str(exc),
            }
        ), 500

    auth_result = transmitter.send_auth_result(
        request_id=request_id,
        face_user_id=user_id,
        similarity_score=confidence,
        liveness_score=0.85,
    )

    backend_status = int(auth_result.get("http_status") or 200)
    status_code = backend_status if backend_status >= 400 else 200
    return (
        jsonify(
            {
                "status": "success" if status_code < 400 else "error",
                "frame_source": frame_source,
                "recognition": {
                    "user_id": user_id,
                    "confidence": confidence,
                },
                "backend_reply": auth_result,
            }
        ),
        status_code,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
