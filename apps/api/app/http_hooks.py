"""HTTP validation, error contracts and readiness registration."""

from app.extensions import db
from app.credential_storage import CredentialStorageError
from app.security_store import SecurePayloadError
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix


def register_http_hooks(app):
    if app.config.get("TRUST_PROXY"):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)

    @app.errorhandler(CredentialStorageError)
    def credential_storage_unavailable(_error):
        db.session.rollback()
        return {
            "msg": "Credential storage unavailable; contact the operator",
            "code": "CREDENTIAL_STORAGE_UNAVAILABLE",
        }, 503

    @app.before_request
    def validate_json_object():
        from flask import request, jsonify

        if request.is_json and not isinstance(request.get_json(silent=True), dict):
            return jsonify(msg="JSON request body must be an object"), 400

    @app.after_request
    def add_cors_headers(response):
        from flask import request

        origin = request.headers.get("Origin")
        if origin and origin in app.config["CORS_ORIGINS"]:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.vary.add("Origin")
            response.headers["Access-Control-Allow-Headers"] = (
                "Content-Type, Authorization, X-CSRF-TOKEN, X-SmartLock-Session"
            )
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.errorhandler(HTTPException)
    def http_error(error):
        response = error.get_response()
        response.data = app.json.dumps(
            dict(status="error", msg=error.description, code=error.name.upper().replace(" ", "_"))
        )
        response.content_type = "application/json"
        return response

    @app.route("/health/live")
    def live():
        return {"status": "ok"}

    @app.route("/health/ready")
    def ready():
        from sqlalchemy.exc import SQLAlchemyError

        try:
            from app.schema import verify_schema

            verify_schema()
            return {"status": "ok"}
        except SQLAlchemyError:
            db.session.rollback()
            return {"status": "unavailable"}, 503

    @app.errorhandler(SecurePayloadError)
    def invalid_secure_payload(error):
        from flask import jsonify

        return jsonify(status="error", msg=str(error), code=error.code), error.status
