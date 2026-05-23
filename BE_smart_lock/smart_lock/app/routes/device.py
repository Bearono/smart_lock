from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from app import db
from app.models import Device


device_bp = Blueprint('device', __name__)


def _mark_online_state(device):
    if not device.last_update:
        device.is_online = False
        return
    device.is_online = datetime.now() - device.last_update <= timedelta(minutes=2)


@device_bp.route('/heartbeat', methods=['POST'])
def heartbeat():
    data = request.get_json() or {}
    device_id = data.get('device_id')
    if not device_id:
        return jsonify({"msg": "device_id is required"}), 400

    device = Device.query.filter_by(device_id=device_id).first()
    if not device:
        device = Device(device_id=device_id)
        db.session.add(device)

    if data.get('lock_status') in ['LOCKED', 'UNLOCKED']:
        device.status = data['lock_status']
    if data.get('battery') is not None:
        device.battery = data['battery']
    if data.get('camera_status'):
        device.camera_status = data['camera_status']

    device.ip_address = data.get('ip') or request.remote_addr
    device.is_online = True
    device.last_update = datetime.now()
    db.session.commit()

    return jsonify({"msg": "Heartbeat received", "device": device.to_dict()}), 200


@device_bp.route('/status', methods=['GET'])
@jwt_required()
def get_device_status():
    device_id = request.args.get('device_id')
    query = Device.query
    if device_id:
        query = query.filter_by(device_id=device_id)

    devices = query.order_by(Device.last_update.desc()).all()
    for device in devices:
        _mark_online_state(device)
    db.session.commit()

    if device_id and not devices:
        return jsonify({"msg": "Device not found"}), 404

    data = [device.to_dict() for device in devices]
    if device_id:
        return jsonify(data[0]), 200
    return jsonify(data), 200
