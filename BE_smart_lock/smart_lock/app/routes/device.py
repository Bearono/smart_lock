from datetime import datetime
import ipaddress

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from app import db
from app.models import Device
from .secure_payload import decrypt_secure_payload
from app.permissions import current_user, permitted_devices, require_device


device_bp = Blueprint('device', __name__)


@device_bp.route('/heartbeat', methods=['POST'])
def heartbeat():
    packet = request.get_json() or {}
    data = decrypt_secure_payload(packet)
    device_id = data.get('device_id')
    if not device_id:
        return jsonify({"msg": "device_id is required"}), 400
    battery = data.get('battery')
    if battery is not None and (type(battery) is not int or not 0 <= battery <= 100):
        return jsonify(msg='Battery must be an integer from 0 to 100'), 400
    if data.get('lock_status') not in (None, 'LOCKED', 'UNLOCKED', 'UNKNOWN'):
        return jsonify(msg='Invalid reported lock status'), 400
    if data.get('camera_status') not in (None, 'ONLINE', 'OFFLINE', 'ERROR', 'UNKNOWN'):
        return jsonify(msg='Invalid camera status'), 400
    try:
        address = str(ipaddress.ip_address(data.get('ip') or request.remote_addr))
    except (ValueError, TypeError):
        return jsonify(msg='Invalid device IP address'), 400

    device = Device.query.filter_by(device_id=device_id).first()
    if not device:
        device = Device(device_id=device_id)
        db.session.add(device)

    if data.get('lock_status') in ['LOCKED', 'UNLOCKED', 'UNKNOWN']:
        device.reported_status = data['lock_status']
    if data.get('battery') is not None:
        device.battery = data['battery']
    if data.get('camera_status'):
        device.camera_status = data['camera_status']

    device.ip_address = address
    device.is_online = True
    device.last_update = datetime.now()
    db.session.commit()

    return jsonify({"msg": "Heartbeat received", "device": device.to_dict()}), 200


@device_bp.route('/status', methods=['GET'])
@jwt_required()
def get_device_status():
    device_id = request.args.get('device_id')
    query = Device.query
    user = current_user()
    if user.role != 'admin':
        query = query.filter(Device.device_id.in_(permitted_devices(user)))
    if device_id:
        require_device(device_id)
        query = query.filter_by(device_id=device_id)

    devices = query.order_by(Device.last_update.desc()).all()

    if device_id and not devices:
        return jsonify({"msg": "Device not found"}), 404

    data = [device.to_dict() for device in devices]
    if device_id:
        return jsonify(data[0]), 200
    return jsonify(data), 200
