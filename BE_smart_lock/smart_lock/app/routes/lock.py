from app.time_contract import timestamp as serialize_time
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app import db
from app.models import AccessLog, Device, UnlockToken, User, GuestPass
from app.door_auth import device_binding
from .secure_payload import decrypt_secure_payload
from app.permissions import require_device, current_user
from app.door_commands import acknowledge, enqueue, refresh, current as current_command
from app.models import DoorCommand
from app.security_store import load_session
from .security_protocol import SecureResponse
from app.validation import text_field

lock_bp = Blueprint('lock', __name__)


def _get_or_create_device(device_id):
    device = Device.query.filter_by(device_id=device_id).first()
    if not device:
        device = Device(device_id=device_id, status='LOCKED')
        db.session.add(device)
        db.session.flush()
    return device


@lock_bp.route('/status', methods=['GET'])
@jwt_required()
def get_status():
    device_id = request.args.get('device_id', 'door_01')
    require_device(device_id)
    device = Device.query.filter_by(device_id=device_id).first_or_404()
    return jsonify({
        "device_id": device.device_id,
        "status": device.status,
        "reported_status": device.reported_status,
        "battery": device.battery,
        "last_update": serialize_time(device.last_update) if device.last_update else None,
    }), 200


@lock_bp.route('/control', methods=['POST'])
@jwt_required()
def control_lock():
    current_user = get_jwt_identity()
    data = request.get_json() or {}
    action = data.get('action')
    device_id = text_field(data, 'device_id', maximum=50)

    if action not in ['LOCK', 'UNLOCK']:
        return jsonify({"msg": "action must be LOCK or UNLOCK"}), 400
    if action == 'UNLOCK':
        return jsonify(msg='Use MFA authentication and consume an unlock token', code='MFA_REQUIRED'), 403
    user = User.query.filter_by(username=current_user).first()
    binding = device_binding(user.id, device_id)
    if not binding:
        return jsonify(msg='Device not bound'), 403

    device = _get_or_create_device(device_id)
    device.status = 'LOCKED'
    command = enqueue(device_id, device.status, user.id)

    db.session.add(AccessLog(
        action='REMOTE_UNLOCK' if action == 'UNLOCK' else 'REMOTE_LOCK',
        username=current_user,
        device_id=device_id, command_id=command.id,
    ))
    db.session.commit()

    return jsonify({
        "status": "success",
        "msg": "Lock command accepted; hardware confirmation pending",
        "command_id": command.id,
        "command_accepted": True,
        "hardware_confirmed": False,
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
    guest_pass = None
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
    command = enqueue(device_id, 'UNLOCKED', user.id,
                      guest_pass_id=guest_pass.id if guest_pass else None)
    unlock_token.command_id = command.id

    db.session.add(AccessLog(
        action='TOKEN_UNLOCK',
        username=user.username if user else 'Unknown',
        device_id=device_id, command_id=command.id,
    ))
    db.session.commit()

    return jsonify({
        "msg": "Unlock token accepted",
        "command_id": command.id,
        "command_expires_at": command.expires_at,
        "device_id": device.device_id,
        "new_status": device.status,
        "command_accepted": True,
        "hardware_confirmed": False,
    }), 200


@lock_bp.route('/sync', methods=['POST'])
def hardware_sync():
    packet = request.get_json() or {}
    data = decrypt_secure_payload(packet)
    device_id = data.get('device_id')
    if not device_id:
        return jsonify({"msg": "device_id is required"}), 400

    device = Device.query.filter_by(device_id=device_id).first()
    if not device:
        return jsonify({"msg": "Device not found"}), 404

    command = current_command(device_id)
    body = {'command': None}
    if command:
        body['command'] = dict(id=command.id, target_status=command.target_status, expires_at=command.expires_at)
    db.session.commit()
    session = load_session(packet['header']['session_id'])
    return jsonify(SecureResponse.sign(session, packet['header'], '/api/lock/sync', body)), 200


@lock_bp.route('/ack', methods=['POST'])
def acknowledge_command():
    data = decrypt_secure_payload(request.get_json() or {})
    command_id = data.get('command_id')
    if not isinstance(command_id, str) or not command_id or len(command_id) > 64:
        return jsonify(msg='A valid command_id is required'), 400
    command = db.session.get(DoorCommand, command_id)
    if not command or command.device_id != data.get('device_id'):
        return jsonify(msg='Command not found'), 404
    result = acknowledge(command, data.get('status'), data.get('reported_status'))
    db.session.commit()
    return jsonify(msg=result.message), result.status_code


@lock_bp.route('/commands/<command_id>')
@jwt_required()
def command_status(command_id):
    command = db.session.get(DoorCommand, command_id)
    if not command:
        return jsonify(msg='Command not found'), 404
    require_device(command.device_id)
    status = refresh(command).status
    db.session.commit()
    return jsonify(id=command.id, status=status, hardware_confirmed=status == 'executed',
                   expires_at=command.expires_at), 200


@lock_bp.route('/command-status', methods=['POST'])
def capability_command_status():
    """Read only the outcome of a consumed bearer token; never enqueue a retry."""
    data = request.get_json() or {}
    token = text_field(data, 'unlock_token')
    device_id = text_field(data, 'device_id', maximum=50)
    capability = UnlockToken.query.filter_by(token=token, device_id=device_id).first()
    if not capability or not capability.command_id:
        return jsonify(msg='No accepted command for this credential'), 404
    command = db.session.get(DoorCommand, capability.command_id)
    if not command:
        return jsonify(msg='Command not found'), 404
    status = refresh(command).status
    db.session.commit()
    return jsonify(id=command.id, status=status, expires_at=command.expires_at,
                   hardware_confirmed=status == 'executed'), 200


@lock_bp.route('/history', methods=['GET'])
@jwt_required()
def get_history():
    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(100, max(1, request.args.get('per_page', 10, type=int)))

    query = AccessLog.query
    user = current_user()
    if user.role != 'admin':
        query = query.filter_by(username=user.username)
    logs_pagination = query.order_by(AccessLog.id.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False,
    )

    results = [{
        "id": log.id,
        "username": log.username,
        "action": log.action,
        "device_id": log.device_id,
        "command_id": log.command_id,
        "timestamp": serialize_time(log.timestamp),
    } for log in logs_pagination.items]

    return jsonify({
        "total": logs_pagination.total,
        "pages": logs_pagination.pages,
        "current_page": logs_pagination.page,
        "data": results,
    }), 200
