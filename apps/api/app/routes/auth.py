"""Password authentication only creates a challenge; TOTP completes login."""

from datetime import datetime, timedelta
import hashlib
import secrets
import base64
from io import BytesIO

import pyotp
import qrcode
from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token,
    jwt_required,
    get_jwt,
    set_access_cookies,
    unset_jwt_cookies,
)
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.passwords import hash_password, verify_password
from app.models import LoginChallenge, LoginRevocation, MFACredential, User
from app.accounts import change_password
from app.permissions import current_user
from app.validation import text_field, totp_code, validate_password, validate_username
from app.authenticators import pending_credential, activate_credential, consume_totp

auth_bp = Blueprint("auth", __name__)


@auth_bp.get("/account/session")
@jwt_required()
def browser_session():
    user = current_user()
    return jsonify(username=user.username, role=user.role)


@auth_bp.post("/logout")
@jwt_required()
def logout():
    import time

    claims = get_jwt()
    LoginRevocation.query.filter(LoginRevocation.expires_at <= time.time()).delete(
        synchronize_session=False
    )
    if db.session.get(LoginRevocation, claims["jti"]) is None:
        db.session.add(LoginRevocation(jti=claims["jti"], expires_at=claims["exp"]))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()  # A concurrent logout may already have revoked this jti.
        if db.session.get(LoginRevocation, claims["jti"]) is None:
            raise
    response = jsonify(msg="Signed out")
    unset_jwt_cookies(response)
    return response


@auth_bp.route("/account/password", methods=["POST"])
@jwt_required()
def update_password():
    data = request.get_json() or {}
    password = text_field(data, "current_password", maximum=72)
    new_password = validate_password(data.get("new_password"))
    code = totp_code(data)
    user = current_user()
    if not verify_password(user, password):
        return jsonify(msg="Current password is incorrect"), 401
    credential = MFACredential.query.filter_by(
        user_id=user.id, credential_type="totp", is_active=True
    ).first()
    if not credential or not consume_totp(credential, code):
        return jsonify(msg="Invalid or already used TOTP code"), 401
    change_password(user, new_password, actor=user.username)
    db.session.commit()
    response = jsonify(msg="Password changed; sign in again", login_required=True)
    unset_jwt_cookies(response)
    return response, 200


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    username, password = data.get("username"), data.get("password")
    validate_username(username)
    if (
        not isinstance(username, str)
        or not username.strip()
        or len(username) > 80
        or not isinstance(password, str)
        or len(password) < 12
        or len(password.encode()) > 72
    ):
        return jsonify(msg="Valid username and password are required"), 400
    user = User(
        username=username, password_hash=hash_password(password), role="user", status="pending"
    )
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(msg="User exists"), 409
    return jsonify(msg="Registration submitted, waiting for admin approval", status="pending"), 201


@auth_bp.route("/login", methods=["POST"])
@auth_bp.route("/login/pre", methods=["POST"])
def prelogin():
    data = request.get_json() or {}
    username, password = data.get("username"), data.get("password")
    if (
        not isinstance(username, str)
        or not isinstance(password, str)
        or not password
        or len(password.encode()) > 72
    ):
        return jsonify(msg="Username and password are required"), 400
    user = User.query.filter_by(username=username).first()
    if not verify_password(user, password):
        return jsonify(msg="Invalid credentials"), 401
    if user.status != "approved":
        return jsonify(msg="Account requires admin approval", status=user.status), 403
    credential = MFACredential.query.filter_by(
        user_id=user.id, credential_type="totp", is_active=True
    ).first()
    binding = credential is None
    if binding:
        credential = pending_credential(user)
        if credential is None:
            db.session.rollback()
            return jsonify(msg="Login state changed; restart login", restart_login=True), 409
    pre_token = secrets.token_urlsafe(32)
    LoginChallenge.query.filter(LoginChallenge.expires_at <= datetime.now()).delete(
        synchronize_session=False
    )
    db.session.add(
        LoginChallenge(
            token_hash=hashlib.sha256(pre_token.encode()).hexdigest(),
            user_id=user.id,
            credential_id=credential.id,
            binding=binding,
            expires_at=datetime.now() + timedelta(minutes=5),
        )
    )
    db.session.commit()
    result = dict(
        pre_token=pre_token,
        totp_bound=not binding,
        role=user.role,
        msg="TOTP binding required" if binding else "MFA required",
    )
    if binding:
        result.update(
            secret=credential.credential_data,
            credential_id=credential.id,
            qr_uri=pyotp.TOTP(credential.credential_data).provisioning_uri(
                name=user.username, issuer_name="SmartLock"
            ),
        )
        output = BytesIO()
        qrcode.make(result["qr_uri"]).save(output, format="PNG")
        result["qr_image"] = "data:image/png;base64," + base64.b64encode(output.getvalue()).decode(
            "ascii"
        )
    return jsonify(result), 200


def _complete_login(binding):
    data = request.get_json() or {}
    pre_token, code = data.get("pre_token"), data.get("code")
    if (
        not isinstance(pre_token, str)
        or not isinstance(code, str)
        or len(code) != 6
        or not code.isdigit()
    ):
        return jsonify(msg="pre_token and a 6-digit code are required"), 400
    challenge = LoginChallenge.query.filter_by(
        token_hash=hashlib.sha256(pre_token.encode()).hexdigest()
    ).first()
    if not challenge or challenge.binding != binding:
        return jsonify(msg="Invalid or expired pre_token", restart_login=True), 401
    reserved = LoginChallenge.query.filter(
        LoginChallenge.id == challenge.id,
        LoginChallenge.consumed.is_(False),
        LoginChallenge.expires_at > datetime.now(),
        LoginChallenge.attempts < 5,
    ).update({LoginChallenge.attempts: LoginChallenge.attempts + 1}, synchronize_session=False)
    if not reserved:
        db.session.rollback()
        return jsonify(msg="Invalid or expired pre_token", restart_login=True), 401
    user = db.session.get(User, challenge.user_id)
    credential = db.session.get(MFACredential, challenge.credential_id)
    if not user or user.status != "approved" or not credential or credential.is_active == binding:
        db.session.commit()
        return jsonify(msg="Login state changed; restart login", restart_login=True), 401
    if not consume_totp(credential, code):
        db.session.commit()
        db.session.refresh(challenge)
        return jsonify(
            msg="Invalid or already used TOTP code", restart_login=challenge.attempts >= 5
        ), 401
    claimed = LoginChallenge.query.filter_by(id=challenge.id, consumed=False).update(
        {LoginChallenge.consumed: True}, synchronize_session=False
    )
    if not claimed:
        db.session.rollback()
        return jsonify(msg="Login challenge already consumed", restart_login=True), 409
    if binding:
        if not activate_credential(user, credential):
            db.session.commit()
            return jsonify(
                msg="Enrollment expired or authenticator already bound; restart login",
                restart_login=True,
            ), 409
    db.session.commit()
    token = create_access_token(
        identity=user.username, additional_claims={"mfa": True, "auth_version": user.auth_version}
    )
    if request.headers.get("X-SmartLock-Session") == "browser":
        response = jsonify(username=user.username, role=user.role)
        set_access_cookies(response, token)
        return response, 200
    # Explicit API clients retain bearer authentication; browsers never persist a token.
    return jsonify(access_token=token, role=user.role), 200


@auth_bp.route("/login/mfa/verify", methods=["POST"])
def verify_mfa():
    return _complete_login(False)


@auth_bp.route("/login/mfa/bind", methods=["POST"])
def bind_totp_with_pre_token():
    return _complete_login(True)
