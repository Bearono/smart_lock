"""Dispatch authenticated face challenges to the approved device endpoint."""

import os
import requests
from flask import current_app
from app.extensions import db
from app.models import Device


class DeviceUnavailable(RuntimeError):
    """Only connection failures may leave a development challenge pending."""


def resolve_device_service_base(device_id):
    from app.models import DeviceProvisioning

    provision = db.session.get(DeviceProvisioning, device_id)
    if provision and provision.enabled:
        return provision.service_url
    if not current_app.config["ALLOW_DEMO_DEVICES"]:
        raise DeviceUnavailable("Device has no approved service endpoint")
    env_key = f"SMART_LOCK_DEVICE_URL_{device_id.upper()}"
    override = os.environ.get(env_key)
    if override:
        return override.rstrip("/")
    global_override = os.environ.get("SMART_LOCK_DEVICE_URL")
    if global_override:
        return global_override.rstrip("/")

    device = Device.query.filter_by(device_id=device_id).first()
    if not device or not device.ip_address:
        return (
            f"{current_app.config['DEVICE_SERVICE_SCHEME']}://"
            f"localhost:{current_app.config['DEVICE_SERVICE_PORT']}"
        )

    raw = device.ip_address.strip()
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw.rstrip("/")
    if ":" in raw and raw.count(":") == 1:
        return f"{current_app.config['DEVICE_SERVICE_SCHEME']}://{raw}"
    return (
        f"{current_app.config['DEVICE_SERVICE_SCHEME']}://"
        f"{raw}:{current_app.config['DEVICE_SERVICE_PORT']}"
    )


def dispatch_face_challenge(device_id, request_id, nonce):
    base_url = resolve_device_service_base(device_id)
    from app.device_commands import signed_command

    body, headers = signed_command(
        device_id, "/auth_challenge", {"request_id": request_id, "nonce": nonce}
    )
    try:
        response = requests.post(
            f"{base_url}/auth_challenge",
            data=body,
            headers=headers,
            allow_redirects=False,
            timeout=current_app.config["DEVICE_SERVICE_TIMEOUT"],
        )
    except (requests.ConnectionError, requests.Timeout) as exc:
        raise DeviceUnavailable(f"Failed to reach device service for {device_id}: {exc}") from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"Device dispatch failed for {device_id}: {exc}") from exc

    # 网关（树莓派）返回非 2xx 时，把它 JSON 里的 message/detail 抽出来一起抛，
    # 前端拿到的 502 才有根因，而不是只有一个 "500 Server Error"。
    if response.status_code >= 300:
        detail = None
        try:
            body = response.json()
            body = body if isinstance(body, dict) else {}
            detail = body.get("detail") or body.get("message") or body.get("msg")
            backend_reply = body.get("backend_reply") or {}
            if not detail and isinstance(backend_reply, dict):
                detail = backend_reply.get("msg") or backend_reply.get("detail")
        except ValueError:
            detail = (response.text or "").strip()[:300]
        raise RuntimeError(
            f"Device {device_id} returned HTTP {response.status_code}: {detail or 'no detail from device'}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"Device {device_id} returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Device {device_id} returned a non-object response")
    backend_reply = payload.get("backend_reply") or {}
    if not isinstance(backend_reply, dict):
        raise RuntimeError(f"Device {device_id} returned an invalid backend reply")
    if payload.get("status") == "error":
        raise RuntimeError(payload.get("message") or f"Device {device_id} reported an error")
    if backend_reply.get("msg") == "Face verification failed":
        raise RuntimeError(f"Device {device_id} completed recognition but face verification failed")

    return {
        "device_url": base_url,
        "frame_source": payload.get("frame_source"),
        "recognition": payload.get("recognition"),
        "backend_reply": backend_reply,
        "snapshot": backend_reply.get("snapshot") or backend_reply.get("snapshot_url"),
    }


def normalize_face_user_id(face_user_id):
    if not face_user_id:
        return face_user_id

    raw_mapping = os.environ.get("SMART_LOCK_FACE_ID_MAP", "").strip()
    if not raw_mapping:
        return face_user_id

    mapping = {}
    for pair in raw_mapping.split(","):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        source, target = pair.split("=", 1)
        source = source.strip()
        target = target.strip()
        if source and target:
            mapping[source] = target

    return mapping.get(face_user_id, face_user_id)
