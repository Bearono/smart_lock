from datetime import datetime, timedelta

import pyotp
import secrets
from flask import Blueprint, request, jsonify
from app import db, bcrypt
from app.models import MFACredential, User
from flask_jwt_extended import create_access_token

auth_bp = Blueprint('auth', __name__)
TEMP_LOGIN_SESSIONS = {}


def _build_login_session(user_id, username, totp_bound, credential_id=None, secret=None):
    pre_token = secrets.token_urlsafe(32)
    TEMP_LOGIN_SESSIONS[pre_token] = {
        "user_id": user_id,
        "username": username,
        "totp_bound": totp_bound,
        "credential_id": credential_id,
        "secret": secret,
        "expires_at": datetime.now() + timedelta(minutes=5),
    }
    return pre_token


def _pop_login_session(pre_token):
    session = TEMP_LOGIN_SESSIONS.get(pre_token)
    if not session:
        return None
    if session["expires_at"] < datetime.now():
        TEMP_LOGIN_SESSIONS.pop(pre_token, None)
        return None
    TEMP_LOGIN_SESSIONS.pop(pre_token, None)
    return session


@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({"msg": "Username and password are required"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"msg": "User exists"}), 400

    hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
    new_user = User(username=username, password_hash=hashed_pw)
    db.session.add(new_user)
    db.session.commit()
    return jsonify({"msg": "Registered successfully"}), 201


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({"msg": "Username and password are required"}), 400

    user = User.query.filter_by(username=username).first()
    if user and bcrypt.check_password_hash(user.password_hash, password):
        token = create_access_token(identity=user.username)
        return jsonify(access_token=token), 200
    return jsonify({"msg": "Invalid credentials"}), 401


@auth_bp.route('/login/pre', methods=['POST'])
def prelogin():
    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({"msg": "Username and password are required"}), 400

    user = User.query.filter_by(username=username).first()
    if not user or not bcrypt.check_password_hash(user.password_hash, password):
        return jsonify({"msg": "Invalid credentials"}), 401

    credential = MFACredential.query.filter_by(
        user_id=user.id,
        credential_type='totp',
        is_active=True,
    ).first()

    if credential:
        pre_token = _build_login_session(user.id, user.username, True)
        return jsonify({
            "pre_token": pre_token,
            "totp_bound": True,
            "msg": "MFA required",
        }), 200

    pending = MFACredential.query.filter_by(
        user_id=user.id,
        credential_type='totp',
        is_active=False,
    ).first()
    if not pending:
        secret = pyotp.random_base32()
        pending = MFACredential(
            user_id=user.id,
            credential_type='totp',
            credential_data=secret,
            is_active=False,
        )
        db.session.add(pending)
        db.session.commit()

    totp = pyotp.TOTP(pending.credential_data)
    pre_token = _build_login_session(
        user.id,
        user.username,
        False,
        credential_id=pending.id,
        secret=pending.credential_data,
    )
    return jsonify({
        "pre_token": pre_token,
        "totp_bound": False,
        "secret": pending.credential_data,
        "qr_uri": totp.provisioning_uri(name=user.username, issuer_name="SmartLock"),
        "credential_id": pending.id,
        "msg": "TOTP binding required",
    }), 200


@auth_bp.route('/login/mfa/verify', methods=['POST'])
def verify_mfa():
    data = request.get_json() or {}
    pre_token = data.get('pre_token')
    code = data.get('code')
    if not pre_token or not code:
        return jsonify({"msg": "pre_token and code are required"}), 400

    session = _pop_login_session(pre_token)
    if not session or not session["totp_bound"]:
        return jsonify({"msg": "Invalid or expired pre_token"}), 401

    credential = MFACredential.query.filter_by(
        user_id=session["user_id"],
        credential_type='totp',
        is_active=True,
    ).first()
    if not credential:
        return jsonify({"msg": "TOTP not bound"}), 400

    if not pyotp.TOTP(credential.credential_data).verify(code, valid_window=1):
        return jsonify({"msg": "Invalid TOTP code"}), 401

    token = create_access_token(identity=session["username"])
    return jsonify(access_token=token), 200


@auth_bp.route('/login/mfa/bind', methods=['POST'])
def bind_totp_with_pre_token():
    data = request.get_json() or {}
    pre_token = data.get('pre_token')
    code = data.get('code')
    if not pre_token or not code:
        return jsonify({"msg": "pre_token and code are required"}), 400

    session = _pop_login_session(pre_token)
    if not session or session["totp_bound"]:
        return jsonify({"msg": "Invalid or expired pre_token"}), 401

    credential = MFACredential.query.get(session["credential_id"])
    if not credential or credential.user_id != session["user_id"]:
        return jsonify({"msg": "Invalid credential"}), 400

    if not pyotp.TOTP(credential.credential_data).verify(code, valid_window=1):
        return jsonify({"msg": "Invalid TOTP code"}), 401

    credential.is_active = True
    db.session.commit()

    token = create_access_token(identity=session["username"])
    return jsonify(access_token=token), 200
