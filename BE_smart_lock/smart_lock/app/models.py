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