"""Private, validated, device-scoped media stored outside the web static root."""
from io import BytesIO
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_file, abort
from flask_jwt_extended import jwt_required

from app import db
from app.models import MediaAsset
from app.permissions import require_device
from app.media_storage import unprotect
from app.media_ingest import save_snapshot_image
from app.secure_payload import decrypt_secure_payload

secure_bp = Blueprint('secure', __name__)





@secure_bp.route('/api/media/<filename>')
@jwt_required()
def media(filename):
    asset = db.session.get(MediaAsset, filename)
    if not asset:
        abort(404)
    require_device(asset.device_id)
    path = Path(current_app.config['UPLOAD_FOLDER']) / asset.filename
    if not path.is_file():
        abort(404)
    content = unprotect(path.read_bytes(), asset.filename, asset.device_id)
    return send_file(BytesIO(content), mimetype='image/jpeg', conditional=False)


@secure_bp.route('/api/snapshot/clear', methods=['POST'])
@jwt_required()
def clear_snapshot():
    data = request.get_json() or {}
    snapshot = data.get('snapshot') or data.get('snapshot_url')
    if not isinstance(snapshot, str) or not snapshot.startswith('/api/media/'):
        return jsonify(msg='A private snapshot path is required'), 400
    filename = snapshot.removeprefix('/api/media/')
    asset = db.session.get(MediaAsset, filename)
    if not asset:
        abort(404)
    require_device(asset.device_id)
    (Path(current_app.config['UPLOAD_FOLDER']) / asset.filename).unlink(missing_ok=True)
    db.session.delete(asset)
    db.session.commit()
    return jsonify(msg='Snapshot cleared'), 200


@secure_bp.route('/api/secure/upload', methods=['POST'])
def handle_rpi_data():
    business = decrypt_secure_payload(request.get_json(), allow_legacy=True)
    try:
        snapshot = save_snapshot_image(business.get('image'), device_id=business.get('device_id'))
    except (ValueError, TypeError):
        return jsonify(status='error', msg='Invalid image'), 400
    db.session.commit()
    return jsonify(status='success', msg='Data received securely', snapshot=snapshot, snapshot_url=snapshot), 200
