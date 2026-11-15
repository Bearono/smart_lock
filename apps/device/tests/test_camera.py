"""Camera backend selection, colour contract and resource recovery."""

import os
from pathlib import Path
import sys
from unittest.mock import Mock, patch
import unittest
import time
from concurrent.futures import Future
from threading import Event
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from camera_core import CameraManager


class CameraTests(unittest.TestCase):
    def test_explicit_csi_backend_never_falls_back_to_wrong_video_node(self):
        with patch.dict(os.environ, {"SMART_LOCK_CAMERA_BACKEND": "picamera2"}):
            manager = CameraManager()
        with (
            patch.object(manager, "_capture_with_picamera2", return_value=None),
            patch.object(manager, "_capture_with_opencv") as usb,
        ):
            self.assertIsNone(manager.capture_frame())
            usb.assert_not_called()
        with self.assertRaises(ValueError):
            CameraManager(backend="invalid")

    def test_picamera2_rgb888_keeps_bgr_channel_order(self):
        frame = np.array([[[255, 0, 0]]], dtype=np.uint8)
        camera = Mock()
        camera.capture_array.return_value.get_result.return_value = frame
        manager = CameraManager(backend="picamera2")
        manager._picamera2 = camera
        self.assertIs(manager.capture_frame(), frame)
        self.assertEqual(manager.capture_frame()[0, 0].tolist(), [255, 0, 0])
        camera.capture_array.assert_called_with(wait=False)

    def test_failure_releases_camera_and_next_capture_can_reinitialize(self):
        camera = Mock()
        camera.capture_array.side_effect = RuntimeError("sensor disconnected")
        manager = CameraManager(backend="picamera2")
        manager._picamera2 = camera
        with self.assertLogs("camera_core", level="ERROR"):
            self.assertIsNone(manager.capture_frame())
        camera.stop.assert_called_once()
        camera.close.assert_called_once()
        self.assertIsNone(manager._picamera2)
        with patch.object(manager, "_capture_with_picamera2", return_value="recovered"):
            self.assertEqual(manager.capture_frame(), "recovered")

    def test_stalled_capture_returns_and_cancels_pending_camera_job(self):
        camera = Mock()
        camera.capture_array.return_value.get_result = Future().result
        manager = CameraManager(backend="picamera2", capture_timeout=0.03)
        manager._picamera2 = camera
        start = time.monotonic()
        with self.assertLogs("camera_core", level="ERROR"):
            self.assertIsNone(manager.capture_frame())
        self.assertLess(time.monotonic() - start, 1.5)
        camera.cancel_all_and_flush.assert_called_once()
        camera.close.assert_called_once()

    def test_stuck_cleanup_quarantines_camera_without_blocking_other_requests(self):
        camera = Mock()
        camera.capture_array.side_effect = TimeoutError("stalled sensor")
        release = Event()
        camera.cancel_all_and_flush.side_effect = lambda: release.wait(5)
        manager = CameraManager(backend="picamera2", capture_timeout=0.03)
        manager._picamera2 = camera
        try:
            with self.assertLogs("camera_core", level="ERROR"):
                self.assertIsNone(manager.capture_frame())
            cleanup = manager._cleanup_thread
            with patch.object(manager, "_capture_frame") as retry:
                start = time.monotonic()
                for _ in range(3):
                    self.assertIsNone(manager.capture_frame())
                self.assertLess(time.monotonic() - start, 0.5)
                retry.assert_not_called()
                self.assertIs(manager._cleanup_thread, cleanup)
        finally:
            release.set()
            manager._cleanup_thread.join(timeout=1)
        with patch.object(manager, "_capture_frame", return_value="new frame"):
            self.assertEqual(manager.capture_frame(), "new frame")

    def test_busy_camera_does_not_exhaust_http_workers(self):
        manager = CameraManager(backend="picamera2", capture_timeout=0.03)
        manager._capture_lock.acquire()
        try:
            start = time.monotonic()
            self.assertIsNone(manager.capture_frame())
            self.assertLess(time.monotonic() - start, 0.5)
        finally:
            manager._capture_lock.release()

    def test_close_is_idempotent_and_opencv_always_releases_capture(self):
        manager = CameraManager(backend="opencv")
        cap = Mock()
        cap.isOpened.return_value = False
        with patch("camera_core.cv2.VideoCapture", return_value=cap):
            self.assertIsNone(manager.capture_frame())
        cap.release.assert_called_once()
        camera = Mock()
        manager._picamera2 = camera
        manager.close()
        manager.close()
        camera.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
