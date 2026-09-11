from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app import db
from app.models import AccessLog, Device, UnlockToken, User, GuestPass
from app.door_auth import device_binding
from .secure_payload import decrypt_secure_payload
from .security_protocol import PROTOCOL_VERSION

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
    if action == 'UNLOCK':
        return jsonify(msg='Use MFA authentication and consume an unlock token', code='MFA_REQUIRED'), 403
    user = User.query.filter_by(username=current_user).first()
    binding = device_binding(user.id, device_id)
    if not binding:
        return jsonify(msg='Device not bound'), 403

    device = _get_or_create_device(device_id)
    device.status = 'UNLOCKED' if action == 'UNLOCK' else 'LOCKED'

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
    device_id = data.get('device_id')

    if not isinstance(token, str) or not isinstance(device_id, str) or not device_id:
        return jsonify({"msg": "unlock_token and device_id are required"}), 400

    unlock_token = UnlockToken.query.filter_by(token=token).first()
    if not unlock_token:
        return jsonify({"msg": "Invalid unlock token"}), 401
    if unlock_token.is_used:
        return jsonify({"msg": "Unlock token already used"}), 401
    if unlock_token.expires_at < datetime.now():
        return jsonify({"msg": "Unlock token expired"}), 401
    if not unlock_token.device_id or unlock_token.device_id != device_id:
        return jsonify(msg='Unlock token is not valid for this device'), 403
    user = db.session.get(User, unlock_token.user_id)
    binding = device_binding(unlock_token.user_id, device_id)
    if not user or user.status != 'approved' or not binding or binding.is_locked:
        return jsonify(msg='Unlock authorization revoked'), 403
    if unlock_token.request_id.startswith('guest_'):
        guest_pass = db.session.get(GuestPass, int(unlock_token.request_id[6:]))
        if not guest_pass or not guest_pass.is_active or guest_pass.valid_until <= datetime.now():
            return jsonify(msg='Guest authorization revoked or expired'), 403

    # Consume and update desired state in one transaction. Exactly one request wins.
    claimed = UnlockToken.query.filter(
        UnlockToken.id == unlock_token.id, UnlockToken.is_used.is_(False),
        UnlockToken.expires_at > datetime.now(), UnlockToken.device_id == device_id,
    ).update({UnlockToken.is_used: True}, synchronize_session=False)
    if not claimed:
        db.session.rollback()
        return jsonify(msg='Unlock token already used or expired'), 409

    device = Device.query.filter_by(device_id=device_id).first()
    if not device:
        device = Device(device_id=device_id)
        db.session.add(device)
    device.status = 'UNLOCKED'

    db.session.add(AccessLog(
        action='TOKEN_UNLOCK',
        username=user.username if user else 'Unknown',
    ))
    db.session.commit()

    return jsonify({
        "msg": "Unlock token accepted",
        "device_id": device.device_id,
        "new_status": device.status,
        "command_accepted": True,
        "hardware_confirmed": False,
    }), 200


@lock_bp.route('/sync', methods=['POST'])
def hardware_sync():
    packet = request.get_json() or {}
    if not isinstance(packet.get('header'), dict) or packet['header'].get('version') != PROTOCOL_VERSION:
        return jsonify(msg='Encrypted v2 payload required'), 401
    try:
        data = decrypt_secure_payload(packet)
    except (ValueError, TypeError, KeyError) as exc:
        return jsonify(msg='Invalid encrypted payload', detail=str(exc)), 400
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
