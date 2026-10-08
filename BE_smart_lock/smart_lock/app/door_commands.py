"""Short-lived commands replace indefinite desired unlock state."""
import time
import uuid
from datetime import datetime
from dataclasses import dataclass
from app import db
from app.models import DoorCommand, GuestPass, User
from app.door_auth import device_binding

COMMAND_TTL_SECONDS = 30
TARGET_STATES = frozenset({'LOCKED', 'UNLOCKED'})


@dataclass(frozen=True)
class Acknowledgement:
    message: str
    status_code: int


def revoke_pending(device_id, user_id=None):
    """Revoke commands in the caller's transaction, including before re-granting."""
    query = DoorCommand.query.filter_by(device_id=device_id, status='pending')
    if user_id is not None:
        query = query.filter_by(user_id=user_id)
    return query.update({'status': 'revoked'}, synchronize_session='fetch')


def refresh(command, now=None):
    """Persist pending-state invalidation without overwriting terminal outcomes.

    The caller owns the transaction. All command read/ack paths use this policy.
    """
    if command.status != 'pending':
        return command
    now = time.time() if now is None else now
    state = None
    if command.expires_at <= now:
        state = 'expired'
    else:
        user = db.session.get(User, command.user_id) if command.user_id else None
        binding = device_binding(command.user_id, command.device_id) if user else None
        if (not user or user.status != 'approved' or not binding
                or (command.target_status == 'UNLOCKED' and binding.is_locked)):
            state = 'revoked'
        if command.guest_pass_id is not None:
            guest = db.session.get(GuestPass, command.guest_pass_id)
            if (not guest or not guest.is_active
                    or not guest.valid_from <= datetime.fromtimestamp(now) < guest.valid_until):
                state = 'revoked'
    if state:
        DoorCommand.query.filter_by(id=command.id, status='pending').update(
            {'status': state}, synchronize_session=False)
        db.session.refresh(command)
    return command


def enqueue(device_id, target_status, user_id, guest_pass_id=None):
    if target_status not in TARGET_STATES:
        raise ValueError('Invalid command target status')
    now = time.time()
    DoorCommand.query.filter_by(device_id=device_id, status='pending').update({'status': 'superseded'})
    command = DoorCommand(id=uuid.uuid4().hex, device_id=device_id, target_status=target_status, user_id=user_id,
                          created_at=now, expires_at=now + COMMAND_TTL_SECONDS, status='pending',
                          guest_pass_id=guest_pass_id)
    db.session.add(command)
    return command


def current(device_id):
    now = time.time()
    DoorCommand.query.filter(DoorCommand.device_id == device_id, DoorCommand.status == 'pending',
                             DoorCommand.expires_at <= now).update({'status': 'expired'})
    command = DoorCommand.query.filter_by(device_id=device_id, status='pending').order_by(DoorCommand.created_at.desc()).first()
    return command if command and refresh(command, now).status == 'pending' else None


def acknowledge(command, status, reported_status):
    """Validate and atomically record a receipt; identical receipts are idempotent."""
    if not isinstance(status, str) or status not in ('executed', 'failed'):
        return Acknowledgement('Invalid command acknowledgement', 400)
    if status == 'executed' and reported_status != command.target_status:
        return Acknowledgement('Sensor state does not confirm the command target', 400)
    now = time.time()
    refresh(command, now)
    if command.status == status:
        return Acknowledgement('Acknowledgement already recorded', 200)
    changed = DoorCommand.query.filter(
        DoorCommand.id == command.id, DoorCommand.status == 'pending',
        DoorCommand.expires_at > now,
    ).update({'status': status, 'acknowledged_at': now}, synchronize_session=False)
    db.session.refresh(command)
    if changed:
        return Acknowledgement('Acknowledgement recorded', 200)
    if command.status == status:
        return Acknowledgement('Acknowledgement already recorded', 200)
    return Acknowledgement('Command expired, revoked, superseded or already acknowledged', 409)
