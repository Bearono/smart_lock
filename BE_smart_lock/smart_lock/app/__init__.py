from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager
from sqlalchemy import inspect, text
from config import Config

# 初始化扩展对象
db = SQLAlchemy()
bcrypt = Bcrypt()
jwt = JWTManager()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # 绑定 app 到扩展
    db.init_app(app)
    bcrypt.init_app(app)
    jwt.init_app(app)

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

    # 注册蓝图
    app.register_blueprint(secure_bp)
    app.register_blueprint(video_bp)
    app.register_blueprint(alarm_bp)
    app.register_blueprint(auth_bp, url_prefix='/api')
    app.register_blueprint(mfa_bp, url_prefix='/api')
    app.register_blueprint(lock_bp, url_prefix='/api/lock')
    app.register_blueprint(device_bp, url_prefix='/api/device')
    app.register_blueprint(face_bp, url_prefix='/api/face')

    with app.app_context():
        # 现在 db.create_all() 会正确扫描到 models 中的所有表
        db.create_all()
        _ensure_schema_columns()

    return app


def _ensure_schema_columns():
    """升级数据库 Schema 以支持防爆破功能"""
    inspector = inspect(db.engine)
    existing_tables = set(inspector.get_table_names())

    column_specs = {
        'devices': {
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
        }
    }

    for table_name, columns in column_specs.items():
        if table_name not in existing_tables:
            continue
        existing_columns = {column['name'] for column in inspector.get_columns(table_name)}
        for column_name, ddl in columns.items():
            if column_name not in existing_columns:
                db.session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"))
    db.session.commit()