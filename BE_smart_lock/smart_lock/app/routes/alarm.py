import os
import time
from flask import Blueprint, request, jsonify, current_app
from app import db, utils
from app.models import AlarmLog

alarm_bp = Blueprint('alarm', __name__)


@alarm_bp.route('/api/trigger_alarm', methods=['POST'])
def trigger_alarm():
    data = request.json
    a_type = data.get('type', '未知异常')
    a_msg = data.get('message', '检测到异常')

    saved_path = "无画面"
    if utils.global_image_obj:
        filename = f"alarm_{int(time.time())}.jpg"
        save_dir = current_app.config['UPLOAD_FOLDER']
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
        filepath = os.path.join(save_dir, filename)
        utils.global_image_obj.save(filepath)
        saved_path = f"/static/captures/{filename}"

    new_alarm = AlarmLog(alarm_type=a_type, message=a_msg, snapshot_path=saved_path)
    db.session.add(new_alarm)
    db.session.commit()

    # 发送邮件
    utils.send_email(current_app.config, a_type, a_msg)

    return jsonify({"status": "success", "snapshot": saved_path}), 200


@alarm_bp.route('/api/alarms', methods=['GET'])
def get_alarms():
    """获取报警日志列表"""
    logs = AlarmLog.query.order_by(AlarmLog.timestamp.desc()).limit(10).all()
    return jsonify([log.to_dict() for log in logs])