from flask import Flask, jsonify, request
from transmit import NetworkTransmitter
from camera_core import CameraManager
import cv2

app = Flask(__name__)

# 初始化模块
BACKEND_URL = "http://192.168.255.131:8000" 
transmitter = NetworkTransmitter(remote_url=BACKEND_URL)
camera = CameraManager()

@app.route('/')
def index():
    return "智能门锁树莓派网关正在运行中..."
    

# 人脸识别并发送UserID
@app.route('/recognition_and_send', methods=['POST'])
def trigger_recognition():
    开启摄像头并拍照
    frame = camera.capture_frame()
    if frame is None:
        return jsonify({"status": "error", "message": "摄像头启动失败"}), 500
    
    # 人脸识别模块
    user_id, conf = recognize(frame)
    # user_id ,conf = 3,3
    # 发送识别结果
    backend_response = transmitter.send_recognition_result(user_id, conf)
    
    if backend_response:
        return jsonify({"status": "success", "backend_reply": backend_response}), 200
    return jsonify({"status": "error", "message": "无法连接到后端服务器"}), 500

# 采集图像上传并在后端展示
@app.route('/capture_and_send', methods=['POST'])
def upload_raw_image():
    # 采集图像
    frame = camera.capture_frame()
    if frame is None:
        return jsonify({"status": "error", "message": "无法获取画面"}), 500
    
    # 传输图片到后端
    upload_result = transmitter.upload_image(frame)
    
    if upload_result:
        return jsonify({"status": "image_sent", "info": upload_result}), 200
    return jsonify({"status": "error", "message": "图片上传失败"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)