import requests
from datetime import datetime
from flask import Blueprint, jsonify, request, current_app, abort
from flask_jwt_extended import jwt_required
from app import db
from app.models import MediaAsset, DeviceProvisioning, AccessLog
from app.device_commands import signed_command
from app.provisioning import validate_device_id
from app.rate_limit import admit
from app.permissions import require_device
from app.time_contract import timestamp

video_bp = Blueprint('video', __name__)


def snapshot_response(asset):
    return jsonify(snapshot='/api/media/' + asset.filename if asset else None,
                   received_at=timestamp(asset.created_at) if asset else None,
                   captured_at=None)


@video_bp.route('/api/video/capture', methods=['POST'])
@jwt_required()
def capture():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not validate_device_id(data.get('device_id')):
        abort(400, description='A valid device_id is required')
    device_id = data['device_id']
    user = require_device(device_id)
    provision = db.session.get(DeviceProvisioning, device_id)
    if not provision or not provision.enabled:
        return jsonify(msg='Device camera service is unavailable'), 503
    if current_app.config.get('RATE_LIMIT_ENABLED', True):
        allowed, retry = admit('camera-capture', f'{user.id}:{device_id}', 6)
        if not allowed:
            return jsonify(msg='Too many capture requests', code='RATE_LIMITED'), 429, {'Retry-After': str(retry)}
    body, headers = signed_command(device_id, '/capture_and_send', {})
    # End the read transaction before the Pi writes its image via another HTTP request.
    origin, username = provision.service_url, user.username
    started = datetime.now()
    db.session.rollback()
    try:
        result = requests.post(origin + '/capture_and_send', data=body, headers=headers,
                               allow_redirects=False, timeout=current_app.config['DEVICE_SERVICE_TIMEOUT'])
        if result.status_code != 200:
            raise ValueError('Device did not confirm image upload')
        payload = result.json()
        path = payload.get('info', {}).get('snapshot') if isinstance(payload, dict) and isinstance(payload.get('info'), dict) else None
        if payload.get('status') != 'image_sent' or not isinstance(path, str) or not path.startswith('/api/media/'):
            raise ValueError('Invalid upload receipt')
        asset = db.session.get(MediaAsset, path.removeprefix('/api/media/'))
        if not asset or asset.device_id != device_id or asset.created_at < started:
            raise ValueError('Upload receipt does not match device media')
    except requests.Timeout:
        return jsonify(msg='Capture result is unknown; refresh stored images before trying again'), 504
    except (requests.RequestException, ValueError, AttributeError):
        return jsonify(msg='Unable to confirm a new camera image'), 502
    db.session.add(AccessLog(username=username, action='SNAPSHOT_CAPTURE', device_id=device_id))
    db.session.commit()
    return snapshot_response(asset), 200


@video_bp.route('/api/upload_frame', methods=['POST'])
def upload_frame():
    return jsonify(msg='Use authenticated encrypted /api/secure/upload', code='SECURE_PROTOCOL_REQUIRED'), 401


@video_bp.route('/video_feed')
def video_feed():
    return jsonify(msg='Use authenticated /api/video/latest and /api/media/<filename>'), 410


@video_bp.route('/api/video/latest')
@jwt_required()
def latest():
    device_id = request.args.get('device_id', '')
    require_device(device_id)
    asset = MediaAsset.query.filter_by(device_id=device_id).order_by(MediaAsset.created_at.desc(), MediaAsset.filename.desc()).first()
    return snapshot_response(asset), 200


@video_bp.route('/')
def index():
    return jsonify(service='smart-lock', status='running'), 200
