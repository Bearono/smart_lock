"""Transactional alarm outbox with bounded retries and expiring worker leases.

SMTP has no exactly-once guarantee: a crash after sending can produce a duplicate.
Alarm records remain authoritative even when email is disabled or exhausted.
"""
from email.message import EmailMessage
import logging
import smtplib
import time
import uuid

from flask import current_app

from app import db
from app.models import AlarmDelivery, AlarmLog

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 5
LEASE_SECONDS = 120


def queue_alarm(alarm):
    db.session.flush()
    enabled = all(current_app.config.get(name) for name in (
        'SMTP_SERVER', 'SENDER_EMAIL', 'SENDER_PASSWORD', 'RECEIVER_EMAIL'))
    db.session.add(AlarmDelivery(alarm_id=alarm.id, status='pending' if enabled else 'disabled'))


def send_alarm(alarm):
    config = current_app.config
    message = EmailMessage()
    message['Subject'] = f'Smart Lock alarm #{alarm.id}: {alarm.alarm_type}'
    message['From'] = config['SENDER_EMAIL']
    message['To'] = config['RECEIVER_EMAIL']
    message.set_content(f'Time: {alarm.timestamp}\n{alarm.message}')
    with smtplib.SMTP_SSL(config['SMTP_SERVER'], config['SMTP_PORT'], timeout=10) as smtp:
        smtp.login(config['SENDER_EMAIL'], config['SENDER_PASSWORD'])
        smtp.send_message(message)


def deliver_pending(limit=20, sender=None):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('Delivery batch size must be between 1 and 100')
    sender = sender or send_alarm
    now = time.time()
    # Attempts are reserved before network I/O. An expired final lease is
    # exhausted even if its worker crashed before recording an outcome.
    AlarmDelivery.query.filter(
        AlarmDelivery.status.in_(['pending', 'sending']),
        AlarmDelivery.next_attempt_at <= now,
        AlarmDelivery.attempts >= MAX_ATTEMPTS,
    ).update({'status': 'failed', 'lease_id': None}, synchronize_session=False)
    db.session.commit()
    candidates = AlarmDelivery.query.filter(
        AlarmDelivery.status.in_(['pending', 'sending']), AlarmDelivery.next_attempt_at <= now,
    ).order_by(AlarmDelivery.next_attempt_at, AlarmDelivery.alarm_id).limit(limit).all()
    ids = [delivery.alarm_id for delivery in candidates]
    db.session.rollback()
    processed = 0
    for alarm_id in ids:
        lease_id = uuid.uuid4().hex
        claimed = AlarmDelivery.query.filter(
            AlarmDelivery.alarm_id == alarm_id,
            AlarmDelivery.status.in_(['pending', 'sending']),
            AlarmDelivery.next_attempt_at <= time.time(),
            AlarmDelivery.attempts < MAX_ATTEMPTS,
        ).update({'status': 'sending', 'lease_id': lease_id,
                  'attempts': AlarmDelivery.attempts + 1,
                  'next_attempt_at': time.time() + LEASE_SECONDS}, synchronize_session=False)
        db.session.commit()
        if not claimed:
            continue
        delivery = db.session.get(AlarmDelivery, alarm_id)
        attempts = delivery.attempts
        alarm = db.session.get(AlarmLog, alarm_id)
        # Detach the payload and release the read transaction before SMTP I/O.
        if alarm is not None:
            db.session.expunge(alarm)
        db.session.rollback()
        try:
            if alarm is None:
                raise ValueError('Alarm payload no longer exists')
            sender(alarm)
            status = 'sent'
        except Exception:
            logger.exception('Alarm email delivery failed for alarm %s', alarm_id)
            status = 'failed' if attempts >= MAX_ATTEMPTS else 'pending'
        AlarmDelivery.query.filter_by(alarm_id=alarm_id, lease_id=lease_id).update({
            'status': status, 'attempts': attempts, 'lease_id': None,
            'next_attempt_at': time.time() + min(3600, 30 * 2 ** attempts),
        }, synchronize_session=False)
        db.session.commit()
        processed += 1
    return processed
