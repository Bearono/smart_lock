from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity

from app import db
from app.models import AlarmLog, AlarmDelivery
from app.notifications import queue_alarm
from .admin import admin_required


alarm_bp = Blueprint('alarm', __name__)


@alarm_bp.route('/api/trigger_alarm', methods=['POST'])
@admin_required
def trigger_alarm():
    data = request.get_json() or {}
    alarm_type = data.get('type', '未知异常')
    message = data.get('message', '检测到异常')
    if not isinstance(alarm_type, str) or not 1 <= len(alarm_type) <= 50 or not isinstance(message, str) or len(message) > 200:
        return jsonify(msg='Invalid alarm type or message'), 400

    saved_path = None

    new_alarm = AlarmLog(
        alarm_type=alarm_type,
        message=message,
        snapshot_path=saved_path,
        status='pending',
    )
    db.session.add(new_alarm)
    queue_alarm(new_alarm)
    db.session.commit()

    return jsonify({"status": "success", "snapshot": saved_path}), 200


@alarm_bp.route('/api/alarms', methods=['GET'])
@admin_required
def get_alarms():
    status = request.args.get('status')
    limit = min(100, max(1, request.args.get('limit', 10, type=int)))

    query = AlarmLog.query
    if status:
        query = query.filter_by(status=status)

    logs = query.order_by(AlarmLog.timestamp.desc()).limit(limit).all()
    deliveries = {item.alarm_id: item.status for item in AlarmDelivery.query.filter(
        AlarmDelivery.alarm_id.in_([log.id for log in logs])).all()}
    return jsonify([dict(log.to_dict(), email_status=deliveries.get(log.id, 'untracked')) for log in logs]), 200


@alarm_bp.route('/api/alarms/<int:alarm_id>', methods=['PATCH'])
@admin_required
def update_alarm(alarm_id):
    data = request.get_json() or {}
    status = data.get('status')
    if status not in ['pending', 'resolved', 'ignored']:
        return jsonify({"msg": "status must be pending, resolved or ignored"}), 400

    alarm = db.session.get(AlarmLog, alarm_id)
    if not alarm:
        return jsonify({"msg": "Alarm not found"}), 404

    alarm.status = status
    alarm.handled_by = get_jwt_identity()
    alarm.handled_at = datetime.now()
    db.session.commit()

    return jsonify(alarm.to_dict()), 200
