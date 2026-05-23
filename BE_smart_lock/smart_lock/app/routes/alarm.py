import os
import time
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app import db, utils
from app.models import AlarmLog


alarm_bp = Blueprint('alarm', __name__)


@alarm_bp.route('/api/trigger_alarm', methods=['POST'])
def trigger_alarm():
    data = request.get_json() or {}
    alarm_type = data.get('type', '未知异常')
    message = data.get('message', '检测到异常')

    saved_path = "无画面"
    if utils.global_image_obj:
        filename = f"alarm_{int(time.time())}.jpg"
        save_dir = current_app.config['UPLOAD_FOLDER']
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
        filepath = os.path.join(save_dir, filename)
        utils.global_image_obj.save(filepath)
        saved_path = f"/static/captures/{filename}"

    new_alarm = AlarmLog(
        alarm_type=alarm_type,
        message=message,
        snapshot_path=saved_path,
        status='pending',
    )
    db.session.add(new_alarm)
    db.session.commit()

    utils.send_email(current_app.config, alarm_type, message)

    return jsonify({"status": "success", "snapshot": saved_path}), 200


@alarm_bp.route('/api/alarms', methods=['GET'])
def get_alarms():
    status = request.args.get('status')
    limit = request.args.get('limit', 10, type=int)

    query = AlarmLog.query
    if status:
        query = query.filter_by(status=status)

    logs = query.order_by(AlarmLog.timestamp.desc()).limit(limit).all()
    return jsonify([log.to_dict() for log in logs]), 200


@alarm_bp.route('/api/alarms/<int:alarm_id>', methods=['PATCH'])
@jwt_required()
def update_alarm(alarm_id):
    data = request.get_json() or {}
    status = data.get('status')
    if status not in ['pending', 'resolved', 'ignored']:
        return jsonify({"msg": "status must be pending, resolved or ignored"}), 400

    alarm = AlarmLog.query.get(alarm_id)
    if not alarm:
        return jsonify({"msg": "Alarm not found"}), 404

    alarm.status = status
    alarm.handled_by = get_jwt_identity()
    alarm.handled_at = datetime.now()
    db.session.commit()

    return jsonify(alarm.to_dict()), 200
