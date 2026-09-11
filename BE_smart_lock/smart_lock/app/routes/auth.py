"""Password authentication only creates a challenge; TOTP completes login."""
from datetime import datetime, timedelta
import hashlib
import secrets

import pyotp
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token
from sqlalchemy.exc import IntegrityError

from app import db, bcrypt
from app.models import LoginChallenge, MFACredential, User

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    username, password = data.get('username'), data.get('password')
    if (not isinstance(username, str) or not username.strip() or len(username) > 80
            or not isinstance(password, str) or not password or len(password.encode()) > 72):
        return jsonify(msg='Valid username and password are required'), 400
    user = User(username=username, password_hash=bcrypt.generate_password_hash(password).decode(),
                role='user', status='pending')
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(msg='User exists'), 409
    return jsonify(msg='Registration submitted, waiting for admin approval', status='pending'), 201


@auth_bp.route('/login', methods=['POST'])
@auth_bp.route('/login/pre', methods=['POST'])
def prelogin():
    data = request.get_json() or {}
    username, password = data.get('username'), data.get('password')
    if (not isinstance(username, str) or not isinstance(password, str)
            or not password or len(password.encode()) > 72):
        return jsonify(msg='Username and password are required'), 400
    user = User.query.filter_by(username=username).first()
    if not user or not bcrypt.check_password_hash(user.password_hash, password):
        return jsonify(msg='Invalid credentials'), 401
    if user.status != 'approved':
        return jsonify(msg='Account requires admin approval', status=user.status), 403
    credential = MFACredential.query.filter_by(
        user_id=user.id, credential_type='totp', is_active=True).first()
    binding = credential is None
    if binding:
        credential = MFACredential.query.filter_by(
            user_id=user.id, credential_type='totp', is_active=False).first()
        if not credential:
            credential = MFACredential(user_id=user.id, credential_type='totp',
                                       credential_data=pyotp.random_base32(), is_active=False)
            db.session.add(credential)
            db.session.flush()
    pre_token = secrets.token_urlsafe(32)
    LoginChallenge.query.filter(LoginChallenge.expires_at <= datetime.now()).delete(synchronize_session=False)
    db.session.add(LoginChallenge(
        token_hash=hashlib.sha256(pre_token.encode()).hexdigest(), user_id=user.id,
        credential_id=credential.id, binding=binding,
        expires_at=datetime.now() + timedelta(minutes=5)))
    db.session.commit()
    result = dict(pre_token=pre_token, totp_bound=not binding, role=user.role,
                  msg='TOTP binding required' if binding else 'MFA required')
    if binding:
        result.update(secret=credential.credential_data, credential_id=credential.id,
                      qr_uri=pyotp.TOTP(credential.credential_data).provisioning_uri(
                          name=user.username, issuer_name='SmartLock'))
    return jsonify(result), 200


def _complete_login(binding):
    data = request.get_json() or {}
    pre_token, code = data.get('pre_token'), data.get('code')
    if not isinstance(pre_token, str) or not isinstance(code, str) or len(code) != 6 or not code.isdigit():
        return jsonify(msg='pre_token and a 6-digit code are required'), 400
    challenge = LoginChallenge.query.filter_by(
        token_hash=hashlib.sha256(pre_token.encode()).hexdigest()).first()
    if not challenge or challenge.binding != binding:
        return jsonify(msg='Invalid or expired pre_token', restart_login=True), 401
    reserved = LoginChallenge.query.filter(
        LoginChallenge.id == challenge.id, LoginChallenge.consumed.is_(False),
        LoginChallenge.expires_at > datetime.now(), LoginChallenge.attempts < 5,
    ).update({LoginChallenge.attempts: LoginChallenge.attempts + 1}, synchronize_session=False)
    if not reserved:
        db.session.rollback()
        return jsonify(msg='Invalid or expired pre_token', restart_login=True), 401
    user = db.session.get(User, challenge.user_id)
    credential = db.session.get(MFACredential, challenge.credential_id)
    if not user or user.status != 'approved' or not credential or credential.is_active == binding:
        db.session.commit()
        return jsonify(msg='Login state changed; restart login', restart_login=True), 401
    if not pyotp.TOTP(credential.credential_data).verify(code, valid_window=1):
        db.session.commit()
        db.session.refresh(challenge)
        return jsonify(msg='Invalid TOTP code', restart_login=challenge.attempts >= 5), 401
    claimed = LoginChallenge.query.filter_by(id=challenge.id, consumed=False).update(
        {LoginChallenge.consumed: True}, synchronize_session=False)
    if not claimed:
        db.session.rollback()
        return jsonify(msg='Login challenge already consumed', restart_login=True), 409
    if binding:
        credential.is_active = True
    db.session.commit()
    return jsonify(access_token=create_access_token(identity=user.username, additional_claims={'mfa': True}),
                   role=user.role), 200


@auth_bp.route('/login/mfa/verify', methods=['POST'])
def verify_mfa():
    return _complete_login(False)


@auth_bp.route('/login/mfa/bind', methods=['POST'])
def bind_totp_with_pre_token():
    return _complete_login(True)
