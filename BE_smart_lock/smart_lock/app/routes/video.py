from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from app.models import MediaAsset
from app.permissions import require_device
from app.time_contract import timestamp

video_bp = Blueprint('video', __name__)


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
    return jsonify(snapshot='/api/media/' + asset.filename if asset else None,
                   received_at=timestamp(asset.created_at) if asset else None,
                   captured_at=None), 200


@video_bp.route('/')
def index():
    return jsonify(service='smart-lock', status='running'), 200
