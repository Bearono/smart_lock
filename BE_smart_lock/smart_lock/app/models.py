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
    camera_status = db.Column(db.String(20), default="UNKNOWN")
    ip_address = db.Column(db.String(45))
    is_online = db.Column(db.Boolean, default=False)
    last_update = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'device_id': self.device_id,
            'status': self.status,
            'battery': self.battery,
            'camera_status': self.camera_status,
            'ip_address': self.ip_address,
            'is_online': self.is_online,
            'last_update': self.last_update.strftime("%Y-%m-%d %H:%M:%S") if self.last_update else None
        }


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
    status = db.Column(db.String(20), default='pending')  # pending, resolved, ignored
    handled_by = db.Column(db.String(80))
    handled_at = db.Column(db.DateTime)

    def to_dict(self):
        return {
            'id': self.id,
            'time': self.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            'type': self.alarm_type,
            'alarm_type': self.alarm_type,
            'message': self.message,
            'snapshot': self.snapshot_path,
            'snapshot_path': self.snapshot_path,
            'status': self.status,
            'handled_by': self.handled_by,
            'handled_at': self.handled_at.strftime("%Y-%m-%d %H:%M:%S") if self.handled_at else None
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

    # ================= 新增：防爆破安全控制字段 =================
    failed_attempts = db.Column(db.Integer, default=0)  # 连续失败次数
    is_locked = db.Column(db.Boolean, default=False)  # 设备是否已被锁定
    # ============================================================

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

    def to_dict(self):
        return {
            'id': self.id,
            'guest_name': self.guest_name,
            'valid_from': self.valid_from.isoformat() if self.valid_from else None,
            'valid_until': self.valid_until.isoformat() if self.valid_until else None,
            'max_uses': self.max_uses,
            'used_count': self.used_count,
            'is_active': self.is_active,
            'created_at': self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None
        }


# 9. 人脸识别日志表
class FaceRecognitionLog(db.Model):
    __tablename__ = 'face_recognition_logs'
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.String(64))
    device_id = db.Column(db.String(50))
    expected_username = db.Column(db.String(80))
    face_user_id = db.Column(db.String(50))
    similarity_score = db.Column(db.Float)
    passed = db.Column(db.Boolean, default=False)
    snapshot_path = db.Column(db.String(200))
    failure_reason = db.Column(db.String(200))
    timestamp = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'request_id': self.request_id,
            'device_id': self.device_id,
            'expected_username': self.expected_username,
            'face_user_id': self.face_user_id,
            'similarity_score': self.similarity_score,
            'passed': self.passed,
            'snapshot': self.snapshot_path,
            'failure_reason': self.failure_reason,
            'timestamp': self.timestamp.strftime("%Y-%m-%d %H:%M:%S") if self.timestamp else None
        }
