from app import db
from datetime import datetime

# 1. 用户表
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

# 2. 设备状态表
class Device(db.Model):
    __tablename__ = 'devices'
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(50), unique=True, nullable=False)
    status = db.Column(db.String(20), default="LOCKED")
    battery = db.Column(db.Integer, default=100)
    last_update = db.Column(db.DateTime, default=datetime.now)

# 3. 访问日志表（控制记录）
class AccessLog(db.Model):
    __tablename__ = 'access_logs'
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    action = db.Column(db.String(100))
    username = db.Column(db.String(80))

# 4. 报警日志表
class AlarmLog(db.Model):
    __tablename__ = 'alarm_logs'
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    alarm_type = db.Column(db.String(50), nullable=False)
    message = db.Column(db.String(200))
    snapshot_path = db.Column(db.String(200))

    def to_dict(self):
        return {
            'id': self.id,
            'time': self.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            'type': self.alarm_type,
            'message': self.message,
            'snapshot': self.snapshot_path
        }

# 5. MFA凭证表（TOTP密钥、设备绑定）
class MFACredential(db.Model):
    __tablename__ = 'mfa_credentials'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    credential_type = db.Column(db.String(20), nullable=False)  # 'totp', 'device'
    credential_data = db.Column(db.String(500), nullable=False)  # TOTP密钥或设备公钥
    device_id = db.Column(db.String(50))  # 设备ID（仅device类型）
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

# 6. 认证会话表
class AuthSession(db.Model):
    __tablename__ = 'auth_sessions'
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.String(64), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    nonce = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, face_verified, totp_required, completed, failed
    device_verified = db.Column(db.Boolean, default=False)
    face_verified = db.Column(db.Boolean, default=False)
    totp_verified = db.Column(db.Boolean, default=False)
    face_user_id = db.Column(db.String(50))
    similarity_score = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.now)
    expires_at = db.Column(db.DateTime)

# 7. 开门令牌表
class UnlockToken(db.Model):
    __tablename__ = 'unlock_tokens'
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(128), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    request_id = db.Column(db.String(64), nullable=False)
    is_used = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    expires_at = db.Column(db.DateTime, nullable=False)

# 8. 访客授权表
class GuestPass(db.Model):
    __tablename__ = 'guest_passes'
    id = db.Column(db.Integer, primary_key=True)
    pass_code = db.Column(db.String(128), unique=True, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    guest_name = db.Column(db.String(80))
    valid_from = db.Column(db.DateTime, nullable=False)
    valid_until = db.Column(db.DateTime, nullable=False)
    max_uses = db.Column(db.Integer, default=1)
    used_count = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)