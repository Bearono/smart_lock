"""Camera backend selection, colour contract and resource recovery."""
import os
from pathlib import Path
import sys
from unittest.mock import Mock, patch
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from camera_core import CameraManager


class CameraTests(unittest.TestCase):
    def test_explicit_csi_backend_never_falls_back_to_wrong_video_node(self):
        with patch.dict(os.environ, {'SMART_LOCK_CAMERA_BACKEND': 'picamera2'}):
            manager = CameraManager()
        with patch.object(manager, '_capture_with_picamera2', return_value=None), patch.object(manager, '_capture_with_opencv') as usb:
            self.assertIsNone(manager.capture_frame())
            usb.assert_not_called()
        with self.assertRaises(ValueError):
            CameraManager(backend='invalid')

    def test_picamera2_rgb888_keeps_bgr_channel_order(self):
        frame = np.array([[[255, 0, 0]]], dtype=np.uint8)
        camera = Mock()
        camera.capture_array.return_value = frame
        manager = CameraManager(backend='picamera2')
        manager._picamera2 = camera
        self.assertIs(manager.capture_frame(), frame)
        self.assertEqual(manager.capture_frame()[0, 0].tolist(), [255, 0, 0])

    def test_failure_releases_camera_and_next_capture_can_reinitialize(self):
        camera = Mock()
        camera.capture_array.side_effect = RuntimeError('sensor disconnected')
        manager = CameraManager(backend='picamera2')
        manager._picamera2 = camera
        with self.assertLogs('camera_core', level='ERROR'):
            self.assertIsNone(manager.capture_frame())
        camera.stop.assert_called_once()
        camera.close.assert_called_once()
        self.assertIsNone(manager._picamera2)
        with patch.object(manager, '_capture_with_picamera2', return_value='recovered'):
            self.assertEqual(manager.capture_frame(), 'recovered')

    def test_close_is_idempotent_and_opencv_always_releases_capture(self):
        manager = CameraManager(backend='opencv')
        cap = Mock()
        cap.isOpened.return_value = False
        with patch('camera_core.cv2.VideoCapture', return_value=cap):
            self.assertIsNone(manager.capture_frame())
        cap.release.assert_called_once()
        camera = Mock()
        manager._picamera2 = camera
        manager.close()
        manager.close()
        camera.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
