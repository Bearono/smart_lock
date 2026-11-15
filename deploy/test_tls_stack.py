"""Verify production TLS and browser sessions in an isolated disposable Compose project.

Requires prebuilt backend/web images and existing local TLS material.
Never mounts the production data volume or production application secrets.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor

import pyotp
import requests

ROOT = Path(__file__).resolve().parents[1]


def verify(output, backend_image='smart-lock-backend:local', web_image='smart-lock-web:local'):
    output.mkdir(parents=True, exist_ok=True)
    report = {'created_at': datetime.now(timezone.utc).isoformat(), 'passed': False,
              'scope': 'isolated production Compose HTTPS and browser session API',
              'images': {'backend': backend_image, 'web': web_image}, 'checks': []}
    project = 'smart-lock-review-' + secrets.token_hex(4)
    with tempfile.TemporaryDirectory(prefix='tls-review-', dir=ROOT / 'releases') as directory:
        temporary = Path(directory)
        for name in ('app_key', 'jwt_key'):
            path = temporary / name
            path.write_text(secrets.token_hex(32), encoding='ascii')
            path.chmod(0o600)
        override = {'services': {name: {'image': backend_image}
                                for name in ('init', 'backend', 'notifications')},
                    'secrets': {name: {'file': str(temporary / name)} for name in ('app_key', 'jwt_key')}}
        override['services']['web'] = {'image': web_image}
        config = temporary / 'override.json'
        config.write_text(json.dumps(override), encoding='utf-8')
        command = ['docker', 'compose', '--project-directory', str(ROOT), '-p', project,
                   '-f', str(ROOT / 'compose.yaml'), '-f', str(ROOT / 'compose.tls.yaml'), '-f', str(config)]
        env = dict(os.environ, SMART_LOCK_WEB_PORT='18080', SMART_LOCK_TLS_PORT='18444',
                   SMART_LOCK_TLS_BIND_IP='127.0.0.1')

        def compose(*args, source=None, private=False):
            result = subprocess.run(command + list(args), input=source, capture_output=True,
                                    text=True, encoding='utf-8', errors='replace', env=env, timeout=180)
            if not private:
                with (output / 'tls-stack.log').open('a', encoding='utf-8') as log:
                    log.write(result.stdout + result.stderr)
            if result.returncode:
                raise RuntimeError('Disposable Compose operation failed: ' + ' '.join(args[:2]))
            return result.stdout

        def check(name, condition):
            if not condition:
                raise AssertionError(name)
            report['checks'].append(name)

        try:
            compose('up', '-d', '--no-build', '--wait', '--wait-timeout', '120')
            # Credentials exist only in this ephemeral database and process memory.
            seed = '''from run import app
from app import db
from app.models import User, MFACredential
from app.passwords import hash_password
import secrets, pyotp, json
with app.app_context():
    password, secret = secrets.token_urlsafe(32), pyotp.random_base32()
    user = User(username='tls_review', status='approved', role='admin', password_hash=hash_password(password))
    db.session.add(user)
    db.session.flush()
    db.session.add(MFACredential(user_id=user.id, credential_type='totp', credential_data=secret, is_active=True))
    db.session.commit()
    print(json.dumps(dict(password=password, secret=secret)))
'''
            identity = json.loads(compose('exec', '-T', 'backend', 'python', '-', source=seed, private=True))
            session = requests.Session()
            session.trust_env = False
            session.verify = str(ROOT / 'deploy/tls/ca.crt')
            base = 'https://localhost:18444'

            def get(path):
                return session.get(base + path, timeout=15)

            def post(path, payload, headers=None):
                return session.post(base + path, json=payload, headers=headers, timeout=15)

            response = get('/')
            check('trusted TLS certificate and frontend response', response.status_code == 200)
            check('TLS response security headers', response.headers.get('X-Frame-Options') == 'DENY'
                  and response.headers.get('X-Content-Type-Options') == 'nosniff')
            check('anonymous session rejected', get('/api/account/session').status_code == 401)
            pre = post('/api/login/pre', {'username': 'tls_review', 'password': identity['password']})
            check('password challenge', pre.status_code == 200 and pre.json()['totp_bound'])
            response = post('/api/login/mfa/verify', {'pre_token': pre.json()['pre_token'],
                            'code': pyotp.TOTP(identity['secret']).now()}, {'X-SmartLock-Session': 'browser'})
            check('MFA browser login without bearer body', response.status_code == 200
                  and 'access_token' not in response.json())
            def parallel_login(_):
                with requests.Session() as client:
                    client.trust_env = False
                    return client.post(base + '/api/login/pre', json={'username': 'tls_review',
                                       'password': identity['password']}, verify=session.verify, timeout=30).status_code
            with ThreadPoolExecutor(max_workers=4) as pool:
                codes = list(pool.map(parallel_login, range(4)))
            check('concurrent scrypt logins fit production memory budget', codes == [200] * 4
                  and get('/health/ready').status_code == 200)
            cookie = next(cookie for cookie in session.cookies if cookie.name == 'smartlock_access')
            check('Secure HttpOnly Strict cookie', cookie.secure and cookie.has_nonstandard_attr('HttpOnly')
                  and cookie.get_nonstandard_attr('SameSite') == 'Strict' and cookie.path == '/api')
            check('authenticated session restored', get('/api/account/session').json().get('username') == 'tls_review')
            check('missing CSRF rejected', post('/api/logout', {}).status_code == 401)
            check('incorrect CSRF rejected', post('/api/logout', {}, {'X-CSRF-TOKEN': 'invalid'}).status_code == 401)
            csrf = session.cookies.get('smartlock_csrf')
            check('valid CSRF logout', post('/api/logout', {}, {'X-CSRF-TOKEN': csrf}).status_code == 200)
            check('browser cookie cleared', get('/api/account/session').status_code == 401)
            session.cookies.set_cookie(cookie)
            check('copied old cookie revoked', get('/api/account/session').status_code == 401)
            compose('restart', 'backend')
            compose('up', '-d', '--no-build', '--wait', '--wait-timeout', '120')
            check('revocation persists across workers and restart', get('/api/account/session').status_code == 401)
            report['passed'] = True
        finally:
            # Only the random project created above is removed, including its test volume.
            try:
                compose('logs', '--tail', '60')
            finally:
                try:
                    compose('down', '-v', '--remove-orphans')
                finally:
                    (output / 'tls-stack.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(f"Production TLS acceptance passed: {len(report['checks'])} checks; disposable stack removed")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'releases/verification')
    parser.add_argument('--backend-image', default='smart-lock-backend:local')
    parser.add_argument('--web-image', default='smart-lock-web:local')
    args = parser.parse_args()
    verify(args.output.resolve(), args.backend_image, args.web_image)
