"""Small request validators shared by routes; validation never writes data."""
from werkzeug.exceptions import BadRequest


def text_field(data, name, *, maximum=128, required=True):
    value = data.get(name)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise BadRequest(f'{name} must be a non-empty string of at most {maximum} characters')
    return value


def totp_code(data, name='code'):
    value = text_field(data, name, maximum=6)
    if len(value) != 6 or not value.isascii() or not value.isdigit():
        raise BadRequest(f'{name} must contain six ASCII digits')
    return value


def validate_password(value):
    if not isinstance(value, str) or len(value) < 12 or len(value.encode('utf-8')) > 72:
        raise BadRequest('Password must contain at least 12 characters and at most 72 bytes')
    return value


def validate_username(value):
    if (not isinstance(value, str) or not value or len(value) > 80
            or value != value.strip() or value.endswith('.') or value in ('.', '..')
            or any(ord(c) < 32 or c in '/\\:*?"<>|' for c in value)):
        raise BadRequest('Username must contain 1-80 characters without surrounding whitespace, path or control characters')
    return value
