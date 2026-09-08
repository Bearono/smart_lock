"""管理员相关接口：用户审批列表、批准/驳回。"""
from datetime import datetime
from functools import wraps

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app import db
from app.models import AccessLog, User


admin_bp = Blueprint('admin', __name__)


def admin_required(fn):
    """要求当前 JWT 身份是 role='admin' 的用户。"""
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        username = get_jwt_identity()
        user = User.query.filter_by(username=username).first()
        if not user or user.role != 'admin':
            return jsonify({"msg": "Admin privilege required"}), 403
        return fn(*args, **kwargs)
    return wrapper


@admin_bp.route('/users', methods=['GET'])
@admin_required
def list_users():
    """列出全部用户，支持按 status 过滤。"""
    status_filter = request.args.get('status')
    query = User.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    users = query.order_by(User.id.desc()).all()
    return jsonify([u.to_dict() for u in users]), 200


@admin_bp.route('/users/pending', methods=['GET'])
@admin_required
def list_pending_users():
    """快捷接口：仅返回待审批用户。"""
    users = User.query.filter_by(status='pending').order_by(User.id.asc()).all()
    return jsonify([u.to_dict() for u in users]), 200


@admin_bp.route('/users/<int:user_id>/approve', methods=['POST'])
@admin_required
def approve_user(user_id):
    target = User.query.get(user_id)
    if not target:
        return jsonify({"msg": "User not found"}), 404
    if target.role == 'admin':
        return jsonify({"msg": "Admin account does not need approval"}), 400

    target.status = 'approved'
    target.approved_at = datetime.now()
    target.approved_by = get_jwt_identity()
    db.session.add(AccessLog(action=f'ADMIN_APPROVE_USER_{target.username}', username=get_jwt_identity()))
    db.session.commit()
    return jsonify({"msg": "User approved", "user": target.to_dict()}), 200


@admin_bp.route('/users/<int:user_id>/reject', methods=['POST'])
@admin_required
def reject_user(user_id):
    target = User.query.get(user_id)
    if not target:
        return jsonify({"msg": "User not found"}), 404
    if target.role == 'admin':
        return jsonify({"msg": "Cannot reject an admin"}), 400

    target.status = 'rejected'
    target.approved_at = None
    target.approved_by = get_jwt_identity()
    db.session.add(AccessLog(action=f'ADMIN_REJECT_USER_{target.username}', username=get_jwt_identity()))
    db.session.commit()
    return jsonify({"msg": "User rejected", "user": target.to_dict()}), 200
