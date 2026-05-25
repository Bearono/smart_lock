import os


class Config:
    # Set DATABASE_URL for MySQL, for example:
    # mysql+pymysql://user:password@localhost/smart_lock_db
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or "sqlite:///smart_lock.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Override these in production so tokens survive process restarts.
    SECRET_KEY = os.environ.get("SECRET_KEY") or os.urandom(32).hex()
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY") or os.urandom(32).hex()

    UPLOAD_FOLDER = os.environ.get(
        "UPLOAD_FOLDER",
        os.path.join(os.getcwd(), "app/static/captures"),
    )

    SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.qq.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
    SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "")
    SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD", "")
    RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL", "")

    DEVICE_SERVICE_SCHEME = os.environ.get("DEVICE_SERVICE_SCHEME", "http")
    DEVICE_SERVICE_PORT = int(os.environ.get("DEVICE_SERVICE_PORT", "5000"))
    DEVICE_SERVICE_TIMEOUT = int(os.environ.get("DEVICE_SERVICE_TIMEOUT", "20"))
    DEVICE_DISPATCH_REQUIRED = os.environ.get("DEVICE_DISPATCH_REQUIRED", "false").lower() == "true"
