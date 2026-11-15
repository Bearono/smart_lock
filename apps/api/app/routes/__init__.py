"""Register the public HTTP surface in one composition point."""


def register_routes(app):
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

    app.register_blueprint(secure_bp)
    app.register_blueprint(security_bp)
    app.register_blueprint(video_bp)
    app.register_blueprint(alarm_bp)
    app.register_blueprint(auth_bp, url_prefix="/api")
    app.register_blueprint(mfa_bp, url_prefix="/api")
    app.register_blueprint(lock_bp, url_prefix="/api/lock")
    app.register_blueprint(device_bp, url_prefix="/api/device")
    app.register_blueprint(face_bp, url_prefix="/api/face")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
