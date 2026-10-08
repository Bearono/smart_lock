"""Validate deployment configuration before any database or network side effects."""
import os


def configure(app):
    production = app.config['DEPLOYMENT_ENV'] == 'production'
    if app.config['DEPLOYMENT_ENV'] not in ('development', 'production'):
        raise ValueError('SMART_LOCK_ENV must be development or production')
    if not 1 <= app.config['SECURITY_SESSION_TTL'] <= 86400:
        raise ValueError('SMART_LOCK_SESSION_TTL must be between 1 and 86400')
    for name in ('SECRET_KEY', 'JWT_SECRET_KEY'):
        key = app.config.get(name)
        if production and (not isinstance(key, str) or len(key.encode()) < 32):
            raise ValueError(f'{name} must be a persistent secret of at least 32 bytes')
        if not key:
            app.config[name] = os.urandom(32).hex()
    if production:
        if app.config['SECRET_KEY'] == app.config['JWT_SECRET_KEY']:
            raise ValueError('SECRET_KEY and JWT_SECRET_KEY must be different')
        for name in ('DEBUG', 'TESTING', 'AUTO_INIT_DB', 'ALLOW_DEMO_DEVICES', 'ALLOW_LEGACY_SECURE_UPLOAD'):
            if app.config.get(name):
                raise ValueError(f'{name} is forbidden in production')
        if not app.config['DEVICE_DISPATCH_REQUIRED']:
            raise ValueError('Production requires device dispatch')
        if not app.config.get('RATE_LIMIT_ENABLED', True):
            raise ValueError('Production requires rate limiting')
        if '*' in app.config['CORS_ORIGINS']:
            raise ValueError('Production requires explicit CORS origins')
    if app.testing:
        # Tests explicitly select their own disposable database.
        app.config['AUTO_INIT_DB'] = True
