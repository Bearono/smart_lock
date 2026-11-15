"""Disposable localhost-only fixture for manual browser acceptance, never production.

Run explicitly: python tests/browser_fixture.py. The database and images live in
a temporary directory and are removed when the process exits normally.
"""
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app, db, bcrypt
from app.models import Device, DeviceGrant, MFACredential, User


if __name__ == '__main__':
    with TemporaryDirectory(prefix='smart-lock-browser-') as directory:
        app = create_app({
            'TESTING': True, 'BCRYPT_LOG_ROUNDS': 4, 'RATE_LIMIT_ENABLED': False,
            'SECRET_KEY': 'disposable-browser-test-app-key-000',
            'JWT_SECRET_KEY': 'disposable-browser-test-jwt-key-000',
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + (Path(directory) / 'fixture.db').as_posix(),
            'UPLOAD_FOLDER': str(Path(directory) / 'captures'),
            'DEVICE_DISPATCH_REQUIRED': False, 'ALLOW_DEMO_DEVICES': True,
        })
        with app.app_context():
            user = User(username='qa_operator', status='approved', role='admin',
                        password_hash=bcrypt.generate_password_hash('local-qa-password').decode())
            db.session.add(user)
            db.session.flush()
            for device_id in ('qa_front', 'qa_back'):
                db.session.add(Device(device_id=device_id, is_online=True, last_update=datetime.now()))
                db.session.add(DeviceGrant(user_id=user.id, device_id=device_id))
                db.session.add(MFACredential(user_id=user.id, credential_type='device', device_id=device_id, credential_data='', is_active=True))
            db.session.commit()
        app.run(host='127.0.0.1', port=8000, debug=False, use_reloader=False)
