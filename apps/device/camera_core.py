import time
import os
import logging
import math
from threading import Lock, Thread

import cv2


class CameraManager:
    def __init__(self, device_index=0, backend=None, capture_timeout=3.0):
        self.device_index = device_index
        self.backend = backend or os.getenv("SMART_LOCK_CAMERA_BACKEND", "auto")
        if self.backend not in ("auto", "picamera2", "opencv"):
            raise ValueError("Unsupported camera backend")
        if not math.isfinite(capture_timeout) or not 0 < capture_timeout <= 30:
            raise ValueError("Camera capture timeout must be within (0, 30] seconds")
        self.capture_timeout = capture_timeout
        self._picamera2 = None
        self._capture_lock = Lock()
        self._cleanup_thread = None

    def _capture_with_picamera2(self):
        if self._picamera2 is None:
            try:
                from picamera2 import Picamera2
            except ImportError:
                return None
            self._picamera2 = Picamera2()
            config = self._picamera2.create_preview_configuration(
                main={"format": "RGB888", "size": (640, 480)}
            )
            self._picamera2.configure(config)
            self._picamera2.start()
            time.sleep(1.0)

        # Picamera2 RGB888 arrays are BGR in memory, already suitable for OpenCV.
        job = self._picamera2.capture_array(wait=False)
        return job.get_result(timeout=self.capture_timeout)

    def _capture_with_opencv(self):
        cap = cv2.VideoCapture(self.device_index)
        try:
            if not cap.isOpened():
                return None
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            ret, frame = cap.read()
            return frame if ret else None
        finally:
            cap.release()

    def capture_frame(self):
        if not self._capture_lock.acquire(timeout=self.capture_timeout):
            return None
        try:
            # A stuck native shutdown must not accumulate new camera owners or threads.
            if self._cleanup_thread is not None and self._cleanup_thread.is_alive():
                return None
            return self._capture_frame()
        except Exception:
            logging.getLogger(__name__).exception("Camera capture failed")
            self._close_picamera2()
            return None
        finally:
            self._capture_lock.release()

    def _close_picamera2(self):
        camera, self._picamera2 = self._picamera2, None
        if camera is not None:
            def release_camera():
                # Timed-out jobs remain queued; cancel them before asking the camera to stop.
                for release in (camera.cancel_all_and_flush, camera.stop, camera.close):
                    try:
                        release()
                    except Exception:
                        logging.getLogger(__name__).exception("Camera release failed")
            self._cleanup_thread = Thread(target=release_camera, name='camera-cleanup', daemon=True)
            self._cleanup_thread.start()
            self._cleanup_thread.join(timeout=0.5)

    def close(self):
        """Release camera ownership on worker shutdown; serialized with capture."""
        if not self._capture_lock.acquire(timeout=self.capture_timeout):
            return
        try:
            self._close_picamera2()
        finally:
            self._capture_lock.release()

    def _capture_frame(self):
        if self.backend == "picamera2":
            return self._capture_with_picamera2()
        if self.backend == "opencv":
            return self._capture_with_opencv()

        frame = self._capture_with_picamera2()
        if frame is not None:
            return frame

        frame = self._capture_with_opencv()
        if frame is None:
            print("Unable to open camera with picamera2 or OpenCV")
        return frame
