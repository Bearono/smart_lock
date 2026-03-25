import json
from flask import Blueprint, request, jsonify
from app import db
from app.models import Device, AccessLog
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timezone

lock_bp = Blueprint('lock', __name__)


# --- 功能一：查看当前门锁状态 ---
# 前端 App 进入首页或控制页时调用
@lock_bp.route('/status', methods=['GET'])
@jwt_required()
def get_status():
    device_id = request.args.get('device_id', 'door_01')
    device = Device.query.filter_by(device_id=device_id).first()

    if not device:
        # 联调方便：如果没有设备则自动创建一个初始状态为关锁的设备
        device = Device(device_id=device_id, status="LOCKED", battery=90)
        db.session.add(device)
        db.session.commit()

    return jsonify({
        "device_id": device.device_id,
        "status": device.status,  # LOCKED 或 UNLOCKED
        "battery": device.battery,
        "last_update": device.last_update.strftime("%Y-%m-%d %H:%M:%S")
    }), 200


# --- 功能二：远程控制门锁开关 ---
# 用户在前端点击“开锁”或“关锁”按钮时调用
@lock_bp.route('/control', methods=['POST'])
@jwt_required()
def control_lock():
    current_user = get_jwt_identity()
    data = request.get_json()

    action = data.get('action')  # 预期值为 'UNLOCK' 或 'LOCK'
    device_id = data.get('device_id', 'door_01')

    if action not in ['LOCK', 'UNLOCK']:
        return jsonify({"msg": "指令无效，必须为 LOCK 或 UNLOCK"}), 400

    device = Device.query.filter_by(device_id=device_id).first()
    if not device:
        return jsonify({"msg": "未找到指定设备"}), 404

    # 更新数据库中的状态
    # 在不使用 MQTT 的情况下，后端直接改变数据库状态
    device.status = action
    device.last_update = datetime.now(timezone.utc)

    # 记录到访问历史表
    log_action = "远程开锁" if action == "UNLOCK" else "远程关锁"
    new_log = AccessLog(action=log_action, username=current_user)

    db.session.add(new_log)
    db.session.commit()

    return jsonify({
        "status": "success",
        "msg": f"指令已下发并更新状态为 {action}",
        "new_status": device.status
    }), 200


# --- 功能三：硬件同步接口（可选，供联调） ---
# 模拟硬件（比如树莓派）主动来询问后端“我该是什么状态”
@lock_bp.route('/sync', methods=['POST'])
def hardware_sync():
    data = request.get_json()
    device_id = data.get('device_id')
    device = Device.query.filter_by(device_id=device_id).first()

    if device:
        return jsonify({"target_status": device.status}), 200
    return jsonify({"msg": "error"}), 404


@lock_bp.route('/history', methods=['GET'])
@jwt_required()
def get_history():
    """
    获取开锁历史记录
    GET /api/lock/history?page=1&per_page=10
    """
    # 获取分页参数，默认第 1 页，每页 10 条
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    # 从数据库查询 AccessLog，按 id 倒序排列（即最新时间在前）
    logs_pagination = AccessLog.query.order_by(AccessLog.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # 构造返回给前端的 JSON
    results = []
    for log in logs_pagination.items:
        results.append({
            "id": log.id,
            "username": log.username,
            "action": log.action,
            # 将 UTC 时间格式化为可读字符串
            "timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        })

    return jsonify({
        "total": logs_pagination.total,
        "pages": logs_pagination.pages,
        "current_page": logs_pagination.page,
        "data": results
    }), 200