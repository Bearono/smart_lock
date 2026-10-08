"""Invalidate derived capabilities in the same transaction as their authority.

Callers own commit/rollback. Re-approving or rebinding must never revive an old
login, authentication challenge, guest pass, token or queued door command.
"""
from sqlalchemy import func

from app import db
from app.models import AuthSession, DoorCommand, GuestPass, LoginChallenge, UnlockToken, User


def revoke_access(user_id: int, device_id: str | None = None) -> None:
    for model in (AuthSession, UnlockToken, DoorCommand):
        query = model.query.filter_by(user_id=user_id)
        if device_id is not None:
            query = query.filter_by(device_id=device_id)
        if model is AuthSession:
            query.filter(model.status.in_(['pending', 'processing', 'face_verified'])).update(
                {'status': 'failed'}, synchronize_session='fetch')
        elif model is UnlockToken:
            query.update({'is_used': True}, synchronize_session='fetch')
        else:
            query.filter_by(status='pending').update({'status': 'revoked'}, synchronize_session='fetch')
    passes = GuestPass.query.filter_by(created_by=user_id)
    if device_id is not None:
        passes = passes.filter_by(device_id=device_id)
    passes.update({'is_active': False}, synchronize_session='fetch')
    if device_id is None:
        LoginChallenge.query.filter_by(user_id=user_id).update(
            {'consumed': True}, synchronize_session='fetch')
        User.query.filter_by(id=user_id).update(
            {User.auth_version: func.coalesce(User.auth_version, 0) + 1}, synchronize_session='fetch')


def revoke_guest(guest_pass: GuestPass) -> None:
    guest_pass.is_active = False
    UnlockToken.query.filter_by(request_id=f'guest_{guest_pass.id}').update(
        {'is_used': True}, synchronize_session='fetch')
    DoorCommand.query.filter_by(guest_pass_id=guest_pass.id, status='pending').update(
        {'status': 'revoked'}, synchronize_session='fetch')
