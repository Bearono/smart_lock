"""Flask application composition; domain services depend on extensions, not this factory."""

from flask import Flask
from config import Config
from app.extensions import db as db, bcrypt as bcrypt, jwt as jwt


def create_app(config_overrides=None):
    from app.deployment import configure
    from app.http_hooks import register_http_hooks
    from app.session_hooks import register_session_hooks
    from app.rate_limit import register as register_rate_limits
    from app.routes import register_routes
    from app.commands import register_commands
    from app.schema import upgrade_schema

    app = Flask(__name__, static_folder=None)
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)
    configure(app)
    db.init_app(app)
    bcrypt.init_app(app)
    jwt.init_app(app)
    register_http_hooks(app)
    register_rate_limits(app)
    register_session_hooks()
    register_routes(app)
    register_commands(app)
    if app.config["AUTO_INIT_DB"]:
        with app.app_context():
            db.create_all()
            upgrade_schema()
    return app
