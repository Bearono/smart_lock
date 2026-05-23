from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager
from config import Config

db = SQLAlchemy()
bcrypt = Bcrypt()
jwt = JWTManager()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    bcrypt.init_app(app)
    jwt.init_app(app)

    # 1. 导入两个独立的蓝图文件
    from app.routes.video import video_bp
    from app.routes.alarm import alarm_bp
    from app.routes.auth import auth_bp
    from app.routes.mfa import mfa_bp
    from app.routes.lock import lock_bp

    from .routes.secure_receiver import secure_bp
    app.register_blueprint(secure_bp)
    # 2. 注册蓝图
    # 视频流注册在根路径，报警接口也注册在根路径，确保 HTML 里的 /api/alarms 能访问到
    app.register_blueprint(video_bp)
    app.register_blueprint(alarm_bp)
    app.register_blueprint(auth_bp, url_prefix='/api')
    app.register_blueprint(mfa_bp, url_prefix='/api')
    app.register_blueprint(lock_bp, url_prefix='/api/lock')

    with app.app_context():
        db.create_all()

    return app
