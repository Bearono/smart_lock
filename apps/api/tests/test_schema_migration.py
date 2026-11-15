from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app, db
from sqlalchemy import inspect


class MigrationTests(unittest.TestCase):
    def test_old_schema_is_upgraded_without_assigning_legacy_permissions(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.db"
            with sqlite3.connect(path) as connection:
                # The new security fields did not exist in the prior schema.
                connection.executescript("""
                    CREATE TABLE auth_sessions (id INTEGER PRIMARY KEY, request_id VARCHAR(64),
                        user_id INTEGER, nonce VARCHAR(64), status VARCHAR(20), device_verified BOOLEAN,
                        face_verified BOOLEAN, totp_verified BOOLEAN, face_user_id VARCHAR(50),
                        similarity_score FLOAT, created_at DATETIME, expires_at DATETIME);
                    CREATE TABLE unlock_tokens (id INTEGER PRIMARY KEY, token VARCHAR(128),
                        user_id INTEGER, request_id VARCHAR(64), is_used BOOLEAN, created_at DATETIME,
                        expires_at DATETIME);
                    CREATE TABLE guest_passes (id INTEGER PRIMARY KEY, pass_code VARCHAR(128),
                        created_by INTEGER, guest_name VARCHAR(80), valid_from DATETIME, valid_until DATETIME,
                        max_uses INTEGER, used_count INTEGER, is_active BOOLEAN, created_at DATETIME);
                    INSERT INTO unlock_tokens (id, token, user_id, request_id, is_used, expires_at)
                        VALUES (1, 'legacy-token', 1, 'legacy-request', 0, '2099-01-01 00:00:00');
                """)
            connection.close()
            config = {
                "TESTING": True,
                "BCRYPT_LOG_ROUNDS": 4,
                "SQLALCHEMY_DATABASE_URI": "sqlite:///" + path.as_posix(),
            }
            for _ in range(2):
                app = create_app(config)
                with app.app_context():
                    inspector = inspect(db.engine)
                    for table in ("auth_sessions", "unlock_tokens", "guest_passes"):
                        self.assertIn(
                            "device_id", {column["name"] for column in inspector.get_columns(table)}
                        )
                    from app.models import UnlockToken

                    self.assertIsNone(db.session.get(UnlockToken, 1).device_id)
                result = app.test_client().post(
                    "/api/lock/unlock-token/verify",
                    json={"unlock_token": "legacy-token", "device_id": "door_01"},
                )
                self.assertEqual(result.status_code, 403, result.json)
                with app.app_context():
                    db.session.remove()
                    db.engine.dispose()


if __name__ == "__main__":
    unittest.main()
