from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from app.models import FaceRecognitionLog
from app.permissions import current_user, permitted_devices


face_bp = Blueprint('face', __name__)


@face_bp.route('/logs', methods=['GET'])
@jwt_required()
def get_face_logs():
    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(100, max(1, request.args.get('per_page', 10, type=int)))
    passed = request.args.get('passed')
    device_id = request.args.get('device_id')

    query = FaceRecognitionLog.query
    user = current_user()
    if user.role != 'admin':
        query = query.filter(FaceRecognitionLog.device_id.in_(permitted_devices(user)))
    if passed is not None:
        query = query.filter_by(passed=passed.lower() == 'true')
    if device_id:
        query = query.filter_by(device_id=device_id)

    logs_pagination = query.order_by(FaceRecognitionLog.id.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False,
    )

    return jsonify({
        "total": logs_pagination.total,
        "pages": logs_pagination.pages,
        "current_page": logs_pagination.page,
        "data": [log.to_dict() for log in logs_pagination.items],
    }), 200
