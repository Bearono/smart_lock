from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from config import Config

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)

    # 1. 导入两个独立的蓝图文件
    from app.routes.video import video_bp
    from app.routes.alarm import alarm_bp

    from .routes.secure_receiver import secure_bp
    app.register_blueprint(secure_bp)
    # 2. 注册蓝图
    # 视频流注册在根路径，报警接口也注册在根路径，确保 HTML 里的 /api/alarms 能访问到
    app.register_blueprint(video_bp)
    app.register_blueprint(alarm_bp)

    with app.app_context():
        db.create_all()

    return app