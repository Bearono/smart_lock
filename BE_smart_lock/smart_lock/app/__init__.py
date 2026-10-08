from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager
from config import Config

# 初始化扩展对象
db = SQLAlchemy()
bcrypt = Bcrypt()
jwt = JWTManager()

def create_app(config_overrides=None):
    app = Flask(__name__, static_folder=None)
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)
    from app.deployment import configure
    configure(app)
    if app.config.get('TRUST_PROXY'):
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)

    @app.before_request
    def validate_json_object():
        from flask import request, jsonify
        if request.is_json and not isinstance(request.get_json(silent=True), dict):
            return jsonify(msg='JSON request body must be an object'), 400

    @app.after_request
    def add_cors_headers(response):
        from flask import request
        origin = request.headers.get('Origin')
        if origin and origin in app.config['CORS_ORIGINS']:
            response.headers['Access-Control-Allow-Origin'] = origin
            response.vary.add('Origin')
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    # 绑定 app 到扩展
    db.init_app(app)
    bcrypt.init_app(app)
    jwt.init_app(app)
    from app.rate_limit import register as register_rate_limits
    register_rate_limits(app)

    from werkzeug.exceptions import HTTPException

    @app.errorhandler(HTTPException)
    def http_error(error):
        from flask import jsonify
        response = error.get_response()
        response.data = app.json.dumps(dict(status='error', msg=error.description,
                                           code=error.name.upper().replace(' ', '_')))
        response.content_type = 'application/json'
        return response

    @app.route('/health/live')
    def live():
        return {'status': 'ok'}

    @app.route('/health/ready')
    def ready():
        from sqlalchemy.exc import SQLAlchemyError
        try:
            from app.schema import verify_schema
            verify_schema()
            return {'status': 'ok'}
        except SQLAlchemyError:
            db.session.rollback()
            return {'status': 'unavailable'}, 503

    from app.security_store import SecurePayloadError

    @app.errorhandler(SecurePayloadError)
    def invalid_secure_payload(error):
        from flask import jsonify
        return jsonify(status='error', msg=str(error), code=error.code), error.status

    @jwt.token_verification_loader
    def verify_login_assurance(_header, payload):
        from app.models import User, MFACredential
        user = User.query.filter_by(username=payload.get('sub')).first()
        return bool(user and user.status == 'approved' and payload.get('mfa') is True
                    and payload.get('auth_version', 0) == user.auth_version
                    and MFACredential.query.filter_by(user_id=user.id, credential_type='totp', is_active=True).first())

    @jwt.token_verification_failed_loader
    def invalid_login_assurance(_header, _payload):
        from flask import jsonify
        return jsonify(msg='MFA login required or account authorization revoked', code='LOGIN_REQUIRED'), 401

    @jwt.expired_token_loader
    def expired_login(_header, _payload):
        from flask import jsonify
        return jsonify(msg='Login expired; sign in again', code='LOGIN_REQUIRED'), 401

    @jwt.invalid_token_loader
    def invalid_login(_reason):
        from flask import jsonify
        return jsonify(msg='Invalid login token', code='LOGIN_REQUIRED'), 401

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

    from app.commands import register_commands
    register_commands(app)
    if app.config['AUTO_INIT_DB']:
        with app.app_context():
            db.create_all()
            _ensure_schema_columns()

    return app



# Compatibility import for existing operator scripts.
from app.schema import upgrade_schema as _ensure_schema_columns
