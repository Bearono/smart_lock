from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager
from sqlalchemy import inspect, text
from datetime import datetime
import os
from config import Config

# 初始化扩展对象
db = SQLAlchemy()
bcrypt = Bcrypt()
jwt = JWTManager()

def create_app(config_overrides=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)

    @app.before_request
    def validate_json_object():
        from flask import request, jsonify
        if request.is_json and not isinstance(request.get_json(silent=True), dict):
            return jsonify(msg='JSON request body must be an object'), 400

    @app.after_request
    def add_cors_headers(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
        return response

    # 绑定 app 到扩展
    db.init_app(app)
    bcrypt.init_app(app)
    jwt.init_app(app)

    @jwt.token_verification_loader
    def verify_login_assurance(_header, payload):
        from app.models import User, MFACredential
        user = User.query.filter_by(username=payload.get('sub')).first()
        return bool(user and user.status == 'approved' and payload.get('mfa') is True
                    and MFACredential.query.filter_by(user_id=user.id, credential_type='totp', is_active=True).first())

    @jwt.token_verification_failed_loader
    def invalid_login_assurance(_header, _payload):
        from flask import jsonify
        return jsonify(msg='MFA login required or account authorization revoked', code='LOGIN_REQUIRED'), 401

    # 【关键修复】在此处显式导入模型，确保 db.create_all() 能发现它们
    from app import models

    # 蓝图导入
    from app.routes.video import video_bp
    from app.routes.alarm import alarm_bp
    from app.routes.auth import auth_bp
    from app.routes.mfa import mfa_bp
    from app.routes.lock import lock_bp
    from app.routes.device import device_bp
    from app.routes.face import face_bp
    from app.routes.secure_receiver import secure_bp
    from app.routes.security import security_bp
    from app.routes.admin import admin_bp

    # 注册蓝图
    app.register_blueprint(secure_bp)
    app.register_blueprint(security_bp)
    app.register_blueprint(video_bp)
    app.register_blueprint(alarm_bp)
    app.register_blueprint(auth_bp, url_prefix='/api')
    app.register_blueprint(mfa_bp, url_prefix='/api')
    app.register_blueprint(lock_bp, url_prefix='/api/lock')
    app.register_blueprint(device_bp, url_prefix='/api/device')
    app.register_blueprint(face_bp, url_prefix='/api/face')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')

    with app.app_context():
        # 现在 db.create_all() 会正确扫描到 models 中的所有表
        db.create_all()
        _ensure_schema_columns()
        _bootstrap_admin()

    return app


def _ensure_schema_columns():
    """升级数据库 Schema 以支持防爆破功能"""
    inspector = inspect(db.engine)
    existing_tables = set(inspector.get_table_names())

    column_specs = {
        # Existing unbound sessions/tokens/passes remain unusable after migration.
        'auth_sessions': {
            'device_id': 'VARCHAR(50)',
            'requires_totp': 'BOOLEAN DEFAULT 0',
        },
        'unlock_tokens': {'device_id': 'VARCHAR(50)'},
        'guest_passes': {'device_id': 'VARCHAR(50)'},
        'devices': {
            'reported_status': "VARCHAR(20) DEFAULT 'UNKNOWN'",
            'camera_status': "VARCHAR(20) DEFAULT 'UNKNOWN'",
            'ip_address': "VARCHAR(45)",
            'is_online': "BOOLEAN DEFAULT 0",
        },
        'alarm_logs': {
            'status': "VARCHAR(20) DEFAULT 'pending'",
            'handled_by': "VARCHAR(80)",
            'handled_at': "DATETIME",
        },
        'mfa_credentials': {
            'failed_attempts': "INTEGER DEFAULT 0",
            'is_locked': "BOOLEAN DEFAULT 0",
        },
        # 旧库升级时，已存在的用户默认放行为 approved，避免演示被卡住。
        'users': {
            'role': "VARCHAR(20) DEFAULT 'user'",
            'status': "VARCHAR(20) DEFAULT 'approved'",
            'created_at': "DATETIME",
            'approved_at': "DATETIME",
            'approved_by': "VARCHAR(80)",
        },
    }

    for table_name, columns in column_specs.items():
        if table_name not in existing_tables:
            continue
        existing_columns = {column['name'] for column in inspector.get_columns(table_name)}
        for column_name, ddl in columns.items():
            if column_name not in existing_columns:
                db.session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"))
    db.session.commit()


def _bootstrap_admin():
    """启动时确保至少存在一个管理员账号。"""
    from app.models import User

    admin_username = os.environ.get("ADMIN_USERNAME", "admin")
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")

    admin = User.query.filter_by(role='admin').first()
    if admin:
        return

    existing = User.query.filter_by(username=admin_username).first()
    if existing:
        existing.role = 'admin'
        existing.status = 'approved'
        if not existing.approved_at:
            existing.approved_at = datetime.now()
        db.session.commit()
        return

    admin = User(
        username=admin_username,
        password_hash=bcrypt.generate_password_hash(admin_password).decode('utf-8'),
        role='admin',
        status='approved',
        approved_at=datetime.now(),
        approved_by='system',
    )
    db.session.add(admin)
    db.session.commit()
