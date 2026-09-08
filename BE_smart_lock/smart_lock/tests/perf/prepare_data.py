"""
性能测试数据准备脚本。

作用:
    - 批量创建 perf_user_001 ~ perf_user_NNN 若干账号
    - 直接把它们置为 approved (跳过 admin 审批, 便于压测)
    - 为每个账号绑定测试设备 PERF_DEVICE_ID (便于 open-door 接口压测)
    - 预置一些 AccessLog / FaceRecognitionLog 让 history 接口有真实数据可读

使用方法 (Windows PowerShell):
    cd BE_smart_lock\smart_lock
    .\.venv\Scripts\Activate.ps1
    python tests\perf\prepare_data.py
    # 想调整数量 / 密码 / 设备号:
    #   $env:PERF_USER_COUNT = "30"; python tests\perf\prepare_data.py

清理:
    python tests\perf\prepare_data.py --cleanup
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]  # smart_lock/
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app import create_app, db, bcrypt  # noqa: E402
from app.models import AccessLog, FaceRecognitionLog, MFACredential, User  # noqa: E402


PERF_USER_PREFIX = os.environ.get("PERF_USER_PREFIX", "perf_user_")
PERF_USER_COUNT = int(os.environ.get("PERF_USER_COUNT", "20"))
PERF_USER_PASSWORD = os.environ.get("PERF_USER_PASSWORD", "Perf@123456")
PERF_DEVICE_ID = os.environ.get("PERF_DEVICE_ID", "door_01")


def _username_for(idx: int) -> str:
    return f"{PERF_USER_PREFIX}{idx:03d}"


def seed():
    app = create_app()
    with app.app_context():
        hashed = bcrypt.generate_password_hash(PERF_USER_PASSWORD).decode("utf-8")

        created = 0
        approved = 0
        bound = 0
        for idx in range(1, PERF_USER_COUNT + 1):
            username = _username_for(idx)
            user = User.query.filter_by(username=username).first()
            if not user:
                user = User(
                    username=username,
                    password_hash=hashed,
                    role="user",
                    status="approved",
                    approved_at=datetime.now(),
                    approved_by="perf_bootstrap",
                )
                db.session.add(user)
                db.session.flush()
                created += 1
            else:
                if user.status != "approved":
                    user.status = "approved"
                    user.approved_at = datetime.now()
                    user.approved_by = "perf_bootstrap"
                    approved += 1
                user.password_hash = hashed

            existing_device = MFACredential.query.filter_by(
                user_id=user.id,
                credential_type="device",
                device_id=PERF_DEVICE_ID,
            ).first()
            if not existing_device:
                db.session.add(MFACredential(
                    user_id=user.id,
                    credential_type="device",
                    credential_data="",
                    device_id=PERF_DEVICE_ID,
                    is_active=True,
                    failed_attempts=0,
                    is_locked=False,
                ))
                bound += 1
            else:
                existing_device.is_active = True
                existing_device.failed_attempts = 0
                existing_device.is_locked = False

        _ensure_history_rows()

        db.session.commit()
        print(
            f"[perf-prepare] users total={PERF_USER_COUNT} newly_created={created} "
            f"re_approved={approved} devices_bound={bound}"
        )
        print(f"[perf-prepare] password: {PERF_USER_PASSWORD}")
        print(f"[perf-prepare] device_id: {PERF_DEVICE_ID}")


def _ensure_history_rows(min_rows: int = 30):
    """给 /api/lock/history 和 /api/face/logs 兜底一批数据, 避免分页返回空。"""
    if AccessLog.query.count() < min_rows:
        for i in range(min_rows):
            db.session.add(AccessLog(
                action="REMOTE_UNLOCK" if i % 2 == 0 else "REMOTE_LOCK",
                username=_username_for((i % PERF_USER_COUNT) + 1),
            ))

    if FaceRecognitionLog.query.count() < min_rows:
        for i in range(min_rows):
            db.session.add(FaceRecognitionLog(
                request_id=f"perf_req_{i:04d}",
                device_id=PERF_DEVICE_ID,
                expected_username=_username_for((i % PERF_USER_COUNT) + 1),
                face_user_id=_username_for((i % PERF_USER_COUNT) + 1),
                similarity_score=0.82 + (i % 10) * 0.01,
                passed=True,
                snapshot_path=None,
                failure_reason=None,
            ))


def cleanup():
    app = create_app()
    with app.app_context():
        usernames = [_username_for(i) for i in range(1, PERF_USER_COUNT + 1)]
        users = User.query.filter(User.username.in_(usernames)).all()
        user_ids = [u.id for u in users]

        removed_creds = MFACredential.query.filter(
            MFACredential.user_id.in_(user_ids)
        ).delete(synchronize_session=False)
        removed_users = User.query.filter(User.id.in_(user_ids)).delete(
            synchronize_session=False,
        )
        db.session.commit()
        print(
            f"[perf-prepare] cleanup done. removed_users={removed_users} "
            f"removed_credentials={removed_creds}"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cleanup", action="store_true", help="删除 perf 测试账号及其设备绑定")
    args = parser.parse_args()
    if args.cleanup:
        cleanup()
    else:
        seed()


if __name__ == "__main__":
    main()
