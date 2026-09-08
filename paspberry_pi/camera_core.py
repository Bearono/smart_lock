import time

import cv2


class CameraManager:
    def __init__(self, device_index=0, backend="auto"):
        self.device_index = device_index
        self.backend = backend
        self._picamera2 = None

    def _capture_with_picamera2(self):
        try:
            from picamera2 import Picamera2
        except ImportError:
            return None

        if self._picamera2 is None:
            self._picamera2 = Picamera2()
            config = self._picamera2.create_preview_configuration(
                main={"format": "RGB888", "size": (640, 480)}
            )
            self._picamera2.configure(config)
            self._picamera2.start()
            time.sleep(1.0)

        frame_rgb = self._picamera2.capture_array()
        if frame_rgb is None:
            return None
        return cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

    def _capture_with_opencv(self):
        cap = cv2.VideoCapture(self.device_index)
        if not cap.isOpened():
            return None

        ret, frame = cap.read()
        cap.release()
        if ret:
            return frame
        return None

    def capture_frame(self):
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
