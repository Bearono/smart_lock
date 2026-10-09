"""Offline image acceptance: imports, synthetic detection and HTTP boundaries.

No camera, GPIO, personal templates or backend network connection is used.
"""
import os
import secrets

os.environ['SMART_LOCK_ENV'] = 'production'
os.environ['BACKEND_URL'] = 'https://backend.invalid'
os.environ['SMART_LOCK_DEVICE_PASSWORD'] = secrets.token_hex(32)
os.environ.pop('SMART_LOCK_DEVICE_PASSWORD_FILE', None)

import cv2
import dlib
import face_recognition
import numpy as np
from app import app
from command_executor import UnavailableActuator
from runtime import CommandWorker, HeartbeatWorker


def main():
    assert face_recognition.face_locations(np.zeros((64, 64, 3), dtype=np.uint8)) == []
    assert UnavailableActuator().read_state() == 'UNKNOWN'
    client = app.test_client()
    assert client.get('/').status_code == 200
    assert client.get('/health/ready').status_code == 503, 'Missing face assets must not appear ready'
    assert client.post('/auth_challenge', json={}).status_code == 401
    assert CommandWorker and HeartbeatWorker
    print(f'Offline device image checks passed: OpenCV {cv2.__version__}, dlib {dlib.__version__}')


if __name__ == '__main__':
    main()
