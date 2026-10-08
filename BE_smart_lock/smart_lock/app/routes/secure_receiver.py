"""Private, validated, device-scoped media stored outside the web static root."""
import base64
from io import BytesIO
from pathlib import Path
import uuid
import warnings

from flask import Blueprint, current_app, jsonify, request, send_file, abort
from flask_jwt_extended import jwt_required
from PIL import Image, UnidentifiedImageError

from app import db
from app.models import MediaAsset
from app.permissions import require_device
from .secure_payload import decrypt_secure_payload

secure_bp = Blueprint('secure', __name__)


def save_snapshot_image(image_b64, prefix='snapshot', device_id=None):
    if not image_b64:
        return None
    if not isinstance(image_b64, str) or not device_id:
        raise ValueError('Image and device identity are required')
    raw = base64.b64decode(image_b64, validate=True)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as image:
                if image.format not in ('JPEG', 'PNG') or image.width * image.height > 4_000_000:
                    raise ValueError('Image must be JPEG/PNG with at most four million pixels')
                image.load()
                output = BytesIO()
                image.convert('RGB').save(output, format='JPEG', quality=85)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError('Invalid image') from exc
    filename = uuid.uuid4().hex + '.jpg'
    directory = Path(current_app.config['UPLOAD_FOLDER'])
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_bytes(output.getvalue())
    db.session.add(MediaAsset(filename=filename, device_id=device_id))
    return '/api/media/' + filename


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
    return send_file(path, mimetype='image/jpeg', conditional=False)


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
