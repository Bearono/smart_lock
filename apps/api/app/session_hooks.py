"""JWT assurance and revocation rules applied to every authenticated request."""

from app.extensions import db, jwt


def register_session_hooks():
    @jwt.token_verification_loader
    def verify_login_assurance(_header, payload):
        from app.models import User, MFACredential

        user = User.query.filter_by(username=payload.get("sub")).first()
        return bool(
            user
            and user.status == "approved"
            and payload.get("mfa") is True
            and payload.get("auth_version", 0) == user.auth_version
            and MFACredential.query.filter_by(
                user_id=user.id, credential_type="totp", is_active=True
            ).first()
        )

    @jwt.token_in_blocklist_loader
    def revoked_login(_header, payload):
        from app.models import LoginRevocation

        return db.session.get(LoginRevocation, payload.get("jti")) is not None

    @jwt.revoked_token_loader
    def rejected_revoked_login(_header, _payload):
        return {"msg": "Login revoked; sign in again", "code": "LOGIN_REQUIRED"}, 401

    @jwt.token_verification_failed_loader
    def invalid_login_assurance(_header, _payload):
        from flask import jsonify

        return jsonify(
            msg="MFA login required or account authorization revoked", code="LOGIN_REQUIRED"
        ), 401

    @jwt.expired_token_loader
    def expired_login(_header, _payload):
        from flask import jsonify

        return jsonify(msg="Login expired; sign in again", code="LOGIN_REQUIRED"), 401

    @jwt.invalid_token_loader
    def invalid_login(_reason):
        from flask import jsonify

        return jsonify(msg="Invalid login token", code="LOGIN_REQUIRED"), 401
