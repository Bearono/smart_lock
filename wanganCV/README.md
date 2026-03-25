# 智能门锁 - 人脸检测服务（OpenCV DNN）

该服务基于 OpenCV DNN 的 Caffe 模型（ResNet-SSD）实现人脸检测，提供 HTTP 接口，便于后台上传图片后进行检测。

> 📖 **详细使用指南**: 查看 [使用指南.md](使用指南.md) 获取完整的功能说明、使用示例和常见问题解答。

## 功能
- 自动下载并缓存模型文件（首次启动时）
- 接收单张图片进行人脸检测
- 返回人脸框像素坐标与置信度
- 提取人脸 embedding（128 维特征向量）
- 将同一用户的多张 embedding 聚合成稳定模板，作为身份签名

## 依赖安装
```bash
pip install -r requirements.txt
```

## 启动服务
```bash
uvicorn app.server:app --host 0.0.0.0 --port 8000
```

首次启动会自动下载模型文件到 `models/` 目录。

## API 说明
- 健康检查：`GET /health`
- 人脸检测：`POST /detect`
  - Form-Data 字段：`file`（图片文件，支持 JPEG/PNG/BMP/WebP）
  - Query 可选参数：`conf_threshold`（默认 0.5）

### 调用示例（curl）
```bash
curl -X POST "http://127.0.0.1:8000/detect?conf_threshold=0.6" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@test.jpg"
```

返回示例：
```json
{
  "image": {"width": 1280, "height": 720},
  "num_faces": 1,
  "faces": [
    {
      "box": {"x1": 320, "y1": 120, "x2": 620, "y2": 520, "width": 300, "height": 400},
      "score": 0.9876
    }
  ]
}
```

## 直接运行（推荐）

无需启动 API 服务器，直接使用命令行工具进行人脸检测：

```bash
# 基本检测
python -m app.detect_faces image.jpg

# 保存裁剪的人脸
python -m app.detect_faces image.jpg --save-crops --output-dir outputs/faces

# 计算 embedding
python -m app.detect_faces image.jpg --embeddings

# 保存 JSON 结果
python -m app.detect_faces image.jpg --output-json result.json

# 调整置信度阈值
python -m app.detect_faces image.jpg --conf-threshold 0.6

# 完整示例（保存裁剪 + 计算 embedding + 保存 JSON）
python -m app.detect_faces image.jpg --save-crops --embeddings --output-json result.json
```

### 命令行参数说明
- `image`: 图片文件路径（必需）
- `--conf-threshold`: 置信度阈值（默认: 0.5）
- `--save-crops`: 保存裁剪的人脸图片
- `--output-dir`: 裁剪图片输出目录（默认: outputs/faces）
- `--margin-ratio`: 裁剪时的 margin 比例（默认: 0.2）
- `--embeddings`: 计算并返回 embedding
- `--output-json`: 将结果保存为 JSON 文件
- `--quiet`: 静默模式，只输出 JSON

## 在代码中直接调用
```python
from app.face_detector import detect_faces_from_path

faces = detect_faces_from_path("path/to/image.jpg", conf_threshold=0.5)
for f in faces:
    print(f["box"], f["score"])
```

## Embedding 聚合功能

### 批量提取 Embedding
从 `manifest_enroll.csv` 读取记录，为每张图片提取 embedding：
```bash
python -m app.extract_embeddings --manifest data/templates/manifest_enroll.csv
```

### 创建用户身份模板
将同一用户的多张 embedding 聚合成一个稳定模板：
```bash
# 使用默认方法（简单平均）
python -m app.template_aggregator

# 使用中位数方法（对异常值更鲁棒）
python -m app.template_aggregator --method median

# 指定自定义目录
python -m app.template_aggregator --embs-dir data/templates/embs --output data/templates/templates
```

### 验证模板质量
验证聚合模板与原始 embedding 的相似度：
```bash
python -m app.verify_template
```

### 聚合方法说明
- **mean（默认）**：简单平均，对噪声有鲁棒性，推荐使用
- **median**：中位数，对异常值更鲁棒
- **weighted_mean**：加权平均，需要提供权重列表

生成的模板文件保存在 `data/templates/templates/` 目录，文件名格式为 `template_{user_id}.npy`。

## 使用方式选择

1. **命令行工具（推荐）**：使用 `python -m app.detect_faces` 直接运行，简单快捷
2. **API 服务**：需要持续服务时，使用 `uvicorn app.server:app` 启动服务器
3. **代码调用**：在 Python 代码中导入函数直接使用

## 注意事项
- 该模型偏向人脸存在性检测，并不输出关键点；若后续需要关键点与对齐，可接入其它模型。
- 摄像头/硬件采集不在本服务内，后台仅需上传图片调用接口即可。
- Embedding 聚合使用 L2 归一化后的特征，确保模板向量长度为 1，便于后续相似度计算。
- 首次运行会自动下载模型文件到 `models/` 目录。

