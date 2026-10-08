"""Explicit additive schema upgrades and readiness verification."""
from sqlalchemy import inspect, text
from app import db


def upgrade_schema():
    """Apply additive compatibility migrations; run offline before serving traffic."""
    inspector = inspect(db.engine)
    existing_tables = set(inspector.get_table_names())

    column_specs = {
        'device_security_sessions': {
            'protocol_version': "VARCHAR(20) NOT NULL DEFAULT 'SL-SEC-v2'",
            'confirmed': 'BOOLEAN NOT NULL DEFAULT 1', 'transcript': 'BLOB',
        },
        'door_commands': {'user_id': 'INTEGER', 'guest_pass_id': 'INTEGER'},
        # Existing unbound sessions/tokens/passes remain unusable after migration.
        'auth_sessions': {
            'device_id': 'VARCHAR(50)',
            'requires_totp': 'BOOLEAN DEFAULT 0',
        },
        'unlock_tokens': {'device_id': 'VARCHAR(50)', 'command_id': 'VARCHAR(32)'},
        'guest_passes': {'device_id': 'VARCHAR(50)'},
        'devices': {
            'display_name': 'VARCHAR(60)',
            'reported_status': "VARCHAR(20) DEFAULT 'UNKNOWN'",
            'camera_status': "VARCHAR(20) DEFAULT 'UNKNOWN'",
            'ip_address': "VARCHAR(45)",
            'is_online': "BOOLEAN DEFAULT 0",
        },
        'access_logs': {'device_id': 'VARCHAR(50)', 'command_id': 'VARCHAR(32)'},
        'alarm_logs': {
            'status': "VARCHAR(20) DEFAULT 'pending'",
            'handled_by': "VARCHAR(80)",
            'handled_at': "DATETIME",
        },
        'mfa_credentials': {
            'failed_attempts': "INTEGER DEFAULT 0",
            'is_locked': "BOOLEAN DEFAULT 0",
        },
        # Legacy users without approval state require an explicit operator review.
        'users': {
            'auth_version': 'INTEGER NOT NULL DEFAULT 0',
            'role': "VARCHAR(20) DEFAULT 'user'",
            'status': "VARCHAR(20) DEFAULT 'pending'",
            'created_at': "DATETIME",
            'approved_at': "DATETIME",
            'approved_by': "VARCHAR(80)",
        },
    }

    for table_name, columns in column_specs.items():
        if table_name not in existing_tables:
            continue
        existing_columns = {column['name'] for column in inspector.get_columns(table_name)}
        for column_name, ddl in columns.items():
            if column_name not in existing_columns:
                db.session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"))
    db.session.commit()


def verify_schema():
    """Check every mapped column without reading application records."""
    for table in db.metadata.sorted_tables:
        db.session.execute(table.select().limit(0))
