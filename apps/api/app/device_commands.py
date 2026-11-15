"""Canonical authenticated commands for operator-provisioned device services."""

from smartlock_protocol.command_auth import sign
from app.provisioning import device_password


def signed_command(device_id, path, payload):
    return sign(device_password(device_id), path, payload)
