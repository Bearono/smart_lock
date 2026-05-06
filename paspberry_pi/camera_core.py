import cv2

class CameraManager:
    def __init__(self, device_index=0):
        self.device_index = device_index

    def capture_frame(self):
        """采集一帧图像"""
        cap = cv2.VideoCapture(self.device_index)
        if not cap.isOpened():
            print("无法打开摄像头")
            return None
        
        # 读取一帧图像
        ret, frame = cap.read()
        cap.release() 
        
        if ret:
            return frame
        return None