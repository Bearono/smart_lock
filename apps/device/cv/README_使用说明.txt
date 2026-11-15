# 智能门锁人脸识别网关 - 文件包说明

## 目录结构

```
给后端的文件包/
│
├── README_使用说明.txt            
│
├── code/
│   ├── __init__.py                  Python 包标识
│   ├── recognize.py                  核心识别函数
│   ├── face_detector.py             人脸检测（被 recognize 调用）
│   ├── verify_template.py            余弦相似度计算（被 recognize 调用）
│   │
│   ├── gateway/                    运行入口在这里
│   │   ├── __init__.py
│   │   ├── app.py                  Flask 入口，运行这个
│   │   ├── transmit.py             加密发送模块
│   │   ├── camera_core.py          摄像头采集
│   │   ├── AesCBCalgorithm.py      AES-CBC 加密
│   │   ├── ECCalgorithm.py         ECC 密钥交换
│   │   ├── requirements.txt        依赖列表
│   │   └── backend_pub.pem        【需要替换】后端 ECC 公钥
│   │
│   └── data/
│       └── templates/
│           └── templates/
│               ├── 【模板文件说明】.txt
│               └── 【这里放入你的 .npy 模板文件】
│
├── models/                          模型文件（建议发，无网络也能用）
│   ├── deploy.prototxt
│   └── res10_300x300_ssd_iter_140000.caffemodel
│
└── outputs/                         测试用降级图片目录
    └── faces/
        └── ...jpg
```

## 使用步骤

### 第一步：安装依赖

```bash
cd code/gateway
pip install -r requirements.txt
```

### 第二步：配置后端公钥

将后端提供的 `backend_pub.pem` 文件内容替换到：

```
code/gateway/backend_pub.pem
```

如果没有这个文件，加密通信会失败。


### 第三步：运行

```bash
cd code/gateway
python app.py
```

服务启动后监听 `0.0.0.0:5000`。

## 接口说明

| 接口 | 方法 | 说明 |
|------|------|------|
| `GET /` | GET | 服务状态 |
| `POST /recognition_and_send` | POST | 拍照 → 人脸识别 → 加密发送到后端 |
| `POST /capture_and_send` | POST | 拍照 → 直接发送图片到后端 |

### /recognition_and_send 响应示例

```json
{
  "status": "success",
  "backend_reply": {
    "status": "success",
    "user_id": "user_001",
    "message": "门锁已开启"
  }
}
```

### 发送的数据格式（加密后发给后端）

```json
{
  "type": "recognition",
  "user_id": "user_001",
  "confidence": 0.8512,
  "timestamp": 1713000000
}
```

## 配置修改

### 后端地址

在 `code/gateway/app.py` 中修改：

```python
BACKEND_URL = "http://192.168.255.131:8000"  # 改成实际后端地址
```

### 识别阈值

在 `code/recognize.py` 的 `recognize()` 函数中：

```python
match_threshold=0.65  # 提高此值减少误识，降低此值减少漏识
```

