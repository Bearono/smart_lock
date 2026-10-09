"""Explicit operator actions; never create or promote users during web startup."""
from datetime import datetime
import click
from flask.cli import with_appcontext
from app import db, bcrypt
from app.models import User
from app.door_commands import revoke_pending
from app.authorization import revoke_access


def register_commands(app):
    @app.cli.command('recover-account')
    @click.option('--username', required=True)
    @click.password_option()
    @click.option('--reset-totp', is_flag=True, help='Require a fresh authenticator enrollment.')
    @with_appcontext
    def recover_account(username, password, reset_totp):
        from app.accounts import change_password
        from werkzeug.exceptions import BadRequest
        user = User.query.filter_by(username=username).first()
        if user is None:
            raise click.ClickException('User not found')
        try:
            change_password(user, password, actor='operator', reset_totp=reset_totp)
        except BadRequest as exc:
            raise click.ClickException(exc.description) from exc
        db.session.commit()
        click.echo('Credentials updated; existing login and door capabilities revoked. Approval and role unchanged.')

    @app.cli.command('prune-media')
    @click.option('--older-than-days', type=click.IntRange(1), required=True)
    @click.option('--limit', type=click.IntRange(1, 10000), default=1000)
    @click.option('--apply', is_flag=True, help='Delete matching media; omitted means preview only.')
    @with_appcontext
    def prune_media_command(older_than_days, limit, apply):
        from app.maintenance import prune_media
        count = prune_media(older_than_days, limit, apply)
        click.echo(f'{count} media assets {"deleted" if apply else "eligible (preview only)"}')

    @app.cli.command('deliver-alarms')
    @click.option('--limit', type=click.IntRange(1, 100), default=20)
    @click.option('--watch', is_flag=True, help='Poll the durable queue every five seconds.')
    @with_appcontext
    def deliver_alarms(limit, watch):
        from app.notifications import deliver_pending
        import time
        while True:
            count = deliver_pending(limit)
            if count:
                click.echo(f'Processed {count} alarm deliveries')
            if not watch:
                return
            time.sleep(5)

    @app.cli.command('init-db')
    @with_appcontext
    def init_db():
        """Initialize or upgrade the schema once, before starting web workers."""
        from app.schema import upgrade_schema
        db.create_all()
        upgrade_schema()
        click.echo('Database initialized. Back up existing databases before upgrading.')

    @app.cli.command('create-admin')
    @click.option('--username', prompt=True)
    @click.password_option()
    @with_appcontext
    def create_admin(username, password):
        """Create a new administrator; existing accounts are never promoted."""
        from app.validation import validate_username
        from werkzeug.exceptions import BadRequest
        try:
            validate_username(username)
        except BadRequest as exc:
            raise click.ClickException(exc.description) from exc
        if not 12 <= len(password) or len(password.encode()) > 72:
            raise click.ClickException('Password must contain at least 12 characters and at most 72 bytes')
        if User.query.filter_by(username=username).first():
            raise click.ClickException('Username already exists; no account was changed')
        db.session.add(User(username=username, password_hash=bcrypt.generate_password_hash(password).decode(),
                            role='admin', status='approved', approved_at=datetime.now(), approved_by='operator'))
        db.session.commit()
        click.echo('Administrator created. First login requires TOTP enrollment.')

    @app.cli.command('provision-device')
    @click.option('--device-id', required=True)
    @click.option('--service-url', required=True)
    @click.password_option()
    @with_appcontext
    def provision_device(device_id, service_url, password):
        """Create or rotate a device secret; all its old sessions are invalidated."""
        from app.models import Device, DeviceProvisioning, DeviceSecuritySession, AuthSession, UnlockToken
        from app.provisioning import validate_device_id, validate_service_url
        from app.security_store import _cipher
        if not validate_device_id(device_id) or len(password.encode()) < 32:
            raise click.ClickException('Use a valid device ID and an independent secret of at least 32 bytes')
        try:
            service_url = validate_service_url(service_url)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
        item = db.session.get(DeviceProvisioning, device_id)
        if not item:
            item = DeviceProvisioning(device_id=device_id)
            db.session.add(item)
        item.encrypted_password = _cipher().encrypt(password.encode())
        item.service_url, item.enabled = service_url, True
        if not Device.query.filter_by(device_id=device_id).first():
            db.session.add(Device(device_id=device_id))
        DeviceSecuritySession.query.filter_by(device_id=device_id).delete()
        AuthSession.query.filter_by(device_id=device_id).update({'status': 'failed'})
        UnlockToken.query.filter_by(device_id=device_id).update({'is_used': True})
        revoke_pending(device_id)
        db.session.commit()
        click.echo('Device provisioned. Install the same secret on this device only.')

    @app.cli.command('grant-device')
    @click.option('--username', required=True)
    @click.option('--device-id', required=True)
    @click.option('--revoke', is_flag=True)
    @with_appcontext
    def grant_device(username, device_id, revoke):
        """Grant/revoke device access; preserves existing security lockouts."""
        from app.access_management import set_device_grant
        user = User.query.filter_by(username=username).first()
        if user is None:
            raise click.ClickException('User not found')
        try:
            set_device_grant(user, device_id, granted=not revoke, actor='operator')
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
        db.session.commit()
        click.echo('Device access revoked.' if revoke else 'Device access granted; user can now bind it.')
