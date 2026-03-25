import requests
import time
import os

# 根据你控制台显示的端口修改，如果是 5000 就用 5000
BASE_URL = "http://127.0.0.1:5000"


def simulate_real_hardware():
    # 路径指向你放在项目根目录下的真实图片
    img_path = os.path.join(os.path.dirname(__file__), 'test.jpg')

    if not os.path.exists(img_path):
        print(f"找不到图片文件：{img_path}，请先放一张 jpg 图片到目录下。")
        return

    print("开始模拟真实硬件上传...")

    # 1. 模拟一次报警
    requests.post(f"{BASE_URL}/api/trigger_alarm", json={
        "type": "手动抓拍",
        "message": "检测到人员经过"
    })

    # 2. 循环上传图片帧，让监控动起来
    with open(img_path, 'rb') as f:
        img_data = f.read()

    while True:
        try:
            # 模拟硬件上传视频帧
            files = {'file': ('frame.jpg', img_data, 'image/jpeg')}
            response = requests.post(f"{BASE_URL}/api/upload_frame", files=files)
            if response.status_code == 200:
                print("帧上传成功...", end='\r')
            time.sleep(0.5)  # 每秒 2 帧
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    simulate_real_hardware()