import base64
import os
import time
from threading import RLock

import cv2
import requests
from requests import HTTPError

from security_protocol import SecureEnvelope, Spake2Client


class NetworkTransmitter:
    def __init__(self, remote_url, device_id=None, device_password=None):
        self.remote_url = remote_url.rstrip("/")
        self.device_id = device_id or os.getenv("SMART_LOCK_DEVICE_ID", "door_01")
        self.device_password = device_password or os.getenv(
            "SMART_LOCK_DEVICE_PASSWORD",
            "ChangeMe-Spake2-Device-Password",
        )
        self.security_session = None
        self._session_lock = RLock()

    def _ensure_secure_session(self):
        if self.security_session and self.security_session.expires_at > time.time() + 10:
            return self.security_session

        client = Spake2Client(self.device_id, self.device_password)
        state, start_msg = client.begin()
        response = requests.post(
            f"{self.remote_url}/api/security/spake2/start",
            json=start_msg,
            timeout=10,
        )
        response.raise_for_status()
        self.security_session = client.finish(state, response.json())
        return self.security_session

    def _send_encrypted_v2(self, endpoint, data_dict, unlock_token=None):
        for attempt in range(2):
            with self._session_lock:
                session = self._ensure_secure_session()
            packet = SecureEnvelope.seal(session, data_dict, unlock_token=unlock_token)
            response = requests.post(f'{self.remote_url}{endpoint}', json=packet, timeout=10)
            try:
                payload = response.json()
            except ValueError:
                response.raise_for_status()
                raise ValueError('Backend returned invalid JSON')
            if not isinstance(payload, dict):
                raise ValueError('Backend returned a non-object response')
            # Only this rejection guarantees the business operation was not executed.
            if attempt == 0 and response.status_code == 401 and payload.get('code') == 'SECURITY_SESSION_INVALID':
                with self._session_lock:
                    if self.security_session is session:
                        self.security_session = None
                continue
            response.raise_for_status()
            if payload.get('status') == 'error':
                raise ValueError(payload.get('msg') or 'Backend rejected secure request')
            return payload

    def _send_encrypted(self, endpoint, data_dict, unlock_token=None):
        try:
            return self._send_encrypted_v2(endpoint, data_dict, unlock_token=unlock_token)
        except HTTPError as exc:
            response = exc.response
            if response is not None:
                try:
                    payload = response.json()
                except ValueError:
                    payload = {"msg": response.text or str(exc)}
                if not isinstance(payload, dict):
                    payload = {'msg': 'Backend rejected request'}
                payload['status'] = 'error'
                payload["http_status"] = response.status_code
                return payload

            return {'status': 'error', 'msg': str(exc), 'http_status': 502}
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            return {'status': 'error', 'msg': str(exc), 'http_status': 502}

    def send_recognition_result(self, user_id, confidence):
        data = {
            "type": "recognition",
            "user_id": user_id,
            "confidence": confidence,
            "timestamp": int(time.time()),
        }
        return self._send_encrypted("/api/secure/upload", data)

    def upload_image(self, frame):
        success, buffer = cv2.imencode(".jpg", frame)
        if not success:
            return {"status": "error", "msg": "Failed to encode image"}

        img_base64 = base64.b64encode(buffer).decode("utf-8")
        data = {
            "type": "image_upload",
            "image": img_base64,
            "timestamp": int(time.time()),
        }
        return self._send_encrypted("/api/secure/upload", data)

    def send_auth_result(self, request_id, face_user_id, similarity_score, liveness_score=None, frame=None, session_nonce=None):
        data = {
            "request_id": request_id,
            "device_id": self.device_id,
            "face_user_id": face_user_id,
            "similarity_score": similarity_score,
            "liveness_score": liveness_score or 0.0,
            "session_nonce": session_nonce,
            "timestamp": int(time.time()),
        }
        if frame is not None:
            success, buffer = cv2.imencode(".jpg", frame)
            if success:
                data["snapshot_image"] = base64.b64encode(buffer).decode("utf-8")
        return self._send_encrypted("/api/mfa/open-door/face-result", data)

    def consume_unlock_token(self, unlock_token):
        """Consume a browser-issued bearer capability; this is not GPIO acknowledgement."""
        response = requests.post(
            f'{self.remote_url}/api/lock/unlock-token/verify',
            json={'device_id': self.device_id, 'unlock_token': unlock_token}, timeout=10)
        response.raise_for_status()
        return response.json()

    def heartbeat(self, lock_status, **status):
        return self._send_encrypted_v2('/api/device/heartbeat',
                                       dict(status, device_id=self.device_id, lock_status=lock_status))

    def sync_lock(self):
        return self._send_encrypted_v2('/api/lock/sync', {'device_id': self.device_id})
