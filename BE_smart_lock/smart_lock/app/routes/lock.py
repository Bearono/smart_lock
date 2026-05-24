from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app import db
from app.models import AccessLog, Device, UnlockToken, User

lock_bp = Blueprint('lock', __name__)


def _get_or_create_device(device_id):
    device = Device.query.filter_by(device_id=device_id).first()
    if not device:
        device = Device(device_id=device_id, status='LOCKED', battery=90)
        db.session.add(device)
        db.session.commit()
    return device


@lock_bp.route('/status', methods=['GET'])
@jwt_required()
def get_status():
    device_id = request.args.get('device_id', 'door_01')
    device = _get_or_create_device(device_id)
    return jsonify({
        "device_id": device.device_id,
        "status": device.status,
        "battery": device.battery,
        "last_update": device.last_update.strftime("%Y-%m-%d %H:%M:%S") if device.last_update else None,
    }), 200


@lock_bp.route('/control', methods=['POST'])
@jwt_required()
def control_lock():
    current_user = get_jwt_identity()
    data = request.get_json() or {}
    action = data.get('action')
    device_id = data.get('device_id', 'door_01')

    if action not in ['LOCK', 'UNLOCK']:
        return jsonify({"msg": "action must be LOCK or UNLOCK"}), 400

    device = _get_or_create_device(device_id)
    device.status = 'UNLOCKED' if action == 'UNLOCK' else 'LOCKED'
    device.last_update = datetime.now()
    device.is_online = True

    db.session.add(AccessLog(
        action='REMOTE_UNLOCK' if action == 'UNLOCK' else 'REMOTE_LOCK',
        username=current_user,
    ))
    db.session.commit()

    return jsonify({
        "status": "success",
        "msg": f"Device status updated to {device.status}",
        "new_status": device.status,
    }), 200


@lock_bp.route('/unlock-token/verify', methods=['POST'])
def verify_unlock_token():
    data = request.get_json() or {}
    token = data.get('unlock_token')
    device_id = data.get('device_id', 'door_01')

    if not token:
        return jsonify({"msg": "unlock_token is required"}), 400

    unlock_token = UnlockToken.query.filter_by(token=token).first()
    if not unlock_token:
        return jsonify({"msg": "Invalid unlock token"}), 401
    if unlock_token.is_used:
        return jsonify({"msg": "Unlock token already used"}), 401
    if unlock_token.expires_at < datetime.now():
        return jsonify({"msg": "Unlock token expired"}), 401

    device = _get_or_create_device(device_id)
    device.status = 'UNLOCKED'
    device.last_update = datetime.now()
    device.is_online = True
    unlock_token.is_used = True

    user = User.query.get(unlock_token.user_id)
    db.session.add(AccessLog(
        action='TOKEN_UNLOCK',
        username=user.username if user else 'Unknown',
    ))
    db.session.commit()

    return jsonify({
        "msg": "Unlock token accepted",
        "device_id": device.device_id,
        "new_status": device.status,
    }), 200


@lock_bp.route('/sync', methods=['POST'])
def hardware_sync():
    data = request.get_json() or {}
    device_id = data.get('device_id')
    if not device_id:
        return jsonify({"msg": "device_id is required"}), 400

    device = Device.query.filter_by(device_id=device_id).first()
    if not device:
        return jsonify({"msg": "Device not found"}), 404

    return jsonify({"target_status": device.status}), 200


@lock_bp.route('/history', methods=['GET'])
@jwt_required()
def get_history():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    logs_pagination = AccessLog.query.order_by(AccessLog.id.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False,
    )

    results = [{
        "id": log.id,
        "username": log.username,
        "action": log.action,
        "timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
    } for log in logs_pagination.items]

    return jsonify({
        "total": logs_pagination.total,
        "pages": logs_pagination.pages,
        "current_page": logs_pagination.page,
        "data": results,
    }), 200
