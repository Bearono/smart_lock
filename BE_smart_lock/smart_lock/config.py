import os
from pathlib import Path


def secret(name):
    filename = os.environ.get(name + '_FILE')
    return Path(filename).read_text(encoding='utf-8').strip() if filename else os.environ.get(name)


class Config:
    # Declare the timezone of existing naive database values; never guess it during upgrades.
    SERVER_TIMEZONE = os.environ.get('SMART_LOCK_SERVER_TIMEZONE') or None
    SECURITY_REPORT_PATH = os.environ.get('SMART_LOCK_SECURITY_REPORT_PATH', '/data/security-report.json')
    DEPLOYMENT_ENV = os.environ.get('SMART_LOCK_ENV', 'development')
    TRUST_PROXY = os.environ.get('TRUST_PROXY', 'false').lower() == 'true'
    AUTO_INIT_DB = os.environ.get('SMART_LOCK_AUTO_INIT_DB', 'false').lower() == 'true'
    ALLOW_DEMO_DEVICES = os.environ.get('SMART_LOCK_ALLOW_DEMO_DEVICES', 'false').lower() == 'true'
    CORS_ORIGINS = [s.strip() for s in os.environ.get('CORS_ORIGINS', '').split(',') if s.strip()]
    # Set DATABASE_URL for MySQL, for example:
    # mysql+pymysql://user:password@localhost/smart_lock_db
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or "sqlite:///smart_lock.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Override these in production so tokens survive process restarts.
    SECRET_KEY = secret('SECRET_KEY')
    JWT_SECRET_KEY = secret('JWT_SECRET_KEY')
    SECURITY_SESSION_TTL = int(os.environ.get('SMART_LOCK_SESSION_TTL', '300'))
    ALLOW_PROTOCOL_V2 = os.environ.get('SMART_LOCK_ALLOW_PROTOCOL_V2', 'true').lower() == 'true'
    ALLOW_LEGACY_SECURE_UPLOAD = os.environ.get('ALLOW_LEGACY_SECURE_UPLOAD', 'false').lower() == 'true'
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024

    UPLOAD_FOLDER = os.environ.get(
        "UPLOAD_FOLDER",
        os.path.join(os.path.dirname(__file__), "instance", "captures"),
    )

    SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.qq.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
    SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "")
    SENDER_PASSWORD = secret('SENDER_PASSWORD') or ''
    RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL", "")

    DEVICE_SERVICE_SCHEME = os.environ.get("DEVICE_SERVICE_SCHEME", "http")
    DEVICE_SERVICE_PORT = int(os.environ.get("DEVICE_SERVICE_PORT", "5000"))
    DEVICE_SERVICE_TIMEOUT = int(os.environ.get("DEVICE_SERVICE_TIMEOUT", "20"))
    DEVICE_DISPATCH_REQUIRED = os.environ.get("DEVICE_DISPATCH_REQUIRED", "true").lower() == "true"
