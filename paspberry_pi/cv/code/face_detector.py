import os
import pathlib
import shutil
import tempfile
import urllib.parse
from typing import List, Dict, Tuple, Optional

import cv2
import numpy as np
import requests

# 获取当前文件所在目录，并计算项目根目录和模型目录
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_CURRENT_DIR)  # code/ 的上一级是项目根目录
_DEFAULT_MODEL_DIR = os.path.join(_PROJECT_ROOT, "models")


CAFFE_PROTO_URL = (
    "https://raw.githubusercontent.com/opencv/opencv/master/samples/dnn/face_detector/deploy.prototxt"
)
CAFFE_MODEL_URL = (
    "https://raw.githubusercontent.com/opencv/opencv_3rdparty/dnn_samples_face_detector_20170830/"
    "res10_300x300_ssd_iter_140000.caffemodel"
)


def _ensure_dir(dir_path: str) -> None:
    if not os.path.isdir(dir_path):
        os.makedirs(dir_path, exist_ok=True)


def _download_file(url: str, target_path: str) -> None:
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    with open(target_path, "wb") as f:
        f.write(response.content)


def _to_opencv_path(path: str) -> str:
    """Convert non-ASCII Windows paths into short paths for OpenCV file APIs."""
    if os.name != "nt":
        return path

    try:
        import ctypes

        buffer_size = 4096
        output = ctypes.create_unicode_buffer(buffer_size)
        result = ctypes.windll.kernel32.GetShortPathNameW(path, output, buffer_size)
        if result:
            return output.value
    except Exception:
        pass

    return path


def _contains_non_ascii(path: str) -> bool:
    return any(ord(ch) > 127 for ch in path)


def _copy_to_ascii_cache(source_path: str) -> str:
    cache_dir = os.path.join(tempfile.gettempdir(), "project_core_cv_models")
    os.makedirs(cache_dir, exist_ok=True)
    target_path = os.path.join(cache_dir, os.path.basename(source_path))

    if (
        not os.path.isfile(target_path)
        or os.path.getsize(target_path) != os.path.getsize(source_path)
        or os.path.getmtime(target_path) < os.path.getmtime(source_path)
    ):
        shutil.copy2(source_path, target_path)

    return target_path


def _prepare_model_paths_for_opencv(proto_path: str, model_path: str) -> Tuple[str, str]:
    if os.name == "nt":
        if _contains_non_ascii(proto_path):
            proto_path = _copy_to_ascii_cache(proto_path)
        if _contains_non_ascii(model_path):
            model_path = _copy_to_ascii_cache(model_path)

    return _to_opencv_path(proto_path), _to_opencv_path(model_path)


def _ensure_models(model_dir: str) -> Tuple[str, str]:
    _ensure_dir(model_dir)
    proto_path = os.path.join(model_dir, "deploy.prototxt")
    model_path = os.path.join(model_dir, "res10_300x300_ssd_iter_140000.caffemodel")

    if not os.path.isfile(proto_path):
        _download_file(CAFFE_PROTO_URL, proto_path)
    if not os.path.isfile(model_path):
        _download_file(CAFFE_MODEL_URL, model_path)

    return proto_path, model_path


class DnnFaceDetector:
    def __init__(self, model_dir: str = None, conf_threshold: float = 0.5):
        self.model_dir = model_dir if model_dir is not None else _DEFAULT_MODEL_DIR
        self.conf_threshold = float(conf_threshold)
        proto_path, model_path = _ensure_models(self.model_dir)
        proto_path, model_path = _prepare_model_paths_for_opencv(proto_path, model_path)
        self.net = cv2.dnn.readNetFromCaffe(proto_path, model_path)

    def detect(self, image_bgr: np.ndarray) -> List[Dict]:
        if image_bgr is None or image_bgr.size == 0:
            return []

        (h, w) = image_bgr.shape[:2]
        blob = cv2.dnn.blobFromImage(
            cv2.resize(image_bgr, (300, 300)),
            scalefactor=1.0,
            size=(300, 300),
            mean=(104.0, 177.0, 123.0),
            swapRB=False,
            crop=False,
        )
        self.net.setInput(blob)
        detections = self.net.forward()

        faces: List[Dict] = []
        # detections shape: [1, 1, N, 7] -> [batch, class, numDetections, (image_id, label, conf, x1, y1, x2, y2)]
        for i in range(detections.shape[2]):
            confidence = float(detections[0, 0, i, 2])
            if confidence < self.conf_threshold:
                continue
            box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
            (x1, y1, x2, y2) = box.astype("int").tolist()

            x1 = max(0, min(x1, w - 1))
            y1 = max(0, min(y1, h - 1))
            x2 = max(0, min(x2, w - 1))
            y2 = max(0, min(y2, h - 1))

            faces.append(
                {
                    "box": {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "width": x2 - x1, "height": y2 - y1},
                    "score": confidence,
                }
            )

        # sort by confidence desc
        faces.sort(key=lambda d: d["score"], reverse=True)
        return faces


def detect_faces_from_path(image_path: str, conf_threshold: float = 0.5) -> List[Dict]:
    image = cv2.imread(image_path)
    detector = DnnFaceDetector(conf_threshold=conf_threshold)
    return detector.detect(image)


def _expand_and_clip_box(x1: int, y1: int, x2: int, y2: int, width: int, height: int, margin_ratio: float) -> Tuple[int, int, int, int]:
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    w = (x2 - x1)
    h = (y2 - y1)
    w_exp = int(round(w * (1.0 + margin_ratio)))
    h_exp = int(round(h * (1.0 + margin_ratio)))
    nx1 = int(round(cx - w_exp / 2.0))
    ny1 = int(round(cy - h_exp / 2.0))
    nx2 = int(round(cx + w_exp / 2.0))
    ny2 = int(round(cy + h_exp / 2.0))
    nx1 = max(0, min(nx1, width - 1))
    ny1 = max(0, min(ny1, height - 1))
    nx2 = max(0, min(nx2, width - 1))
    ny2 = max(0, min(ny2, height - 1))
    if nx2 <= nx1:
        nx2 = min(width - 1, nx1 + 1)
    if ny2 <= ny1:
        ny2 = min(height - 1, ny1 + 1)
    return nx1, ny1, nx2, ny2


def crop_and_save_faces(image_bgr: np.ndarray, faces: List[Dict], output_dir: str, filename_prefix: str = "face", margin_ratio: float = 0.2) -> List[Dict]:
    if image_bgr is None or image_bgr.size == 0:
        return []
    # resolve absolute output directory to avoid cwd issues
    abs_output_dir = os.path.abspath(output_dir)
    os.makedirs(abs_output_dir, exist_ok=True)
    h, w = image_bgr.shape[:2]
    saved: List[Dict] = []
    for idx, f in enumerate(faces):
        b = f.get("box", {})
        x1, y1, x2, y2 = int(b.get("x1", 0)), int(b.get("y1", 0)), int(b.get("x2", 0)), int(b.get("y2", 0))
        ex1, ey1, ex2, ey2 = _expand_and_clip_box(x1, y1, x2, y2, w, h, margin_ratio)
        crop = image_bgr[ey1:ey2, ex1:ex2]
        filename = f"{filename_prefix}_{idx+1}.jpg"
        filepath = os.path.join(abs_output_dir, filename)
        if crop.size == 0:
            continue
        try:
            from PIL import Image
            rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
            img.save(filepath, format="JPEG")
        except Exception:
            continue
        saved.append({
            "file": filepath,
            "box": {"x1": ex1, "y1": ey1, "x2": ex2, "y2": ey2, "width": ex2 - ex1, "height": ey2 - ey1},
            "score": f.get("score", 0.0),
        })
    return saved


def compute_embeddings(
    image_bgr: np.ndarray,
    faces: List[Dict],
    margin_ratio: float = 0.0,
) -> List[Dict]:
    """使用 face_recognition 计算 embedding。

    margin_ratio 用于在计算 embedding 时扩展检测框，保持与裁剪一致。
    返回列表包含 embedding (128 维) 及对应的框与置信度。
    """

    if image_bgr is None or image_bgr.size == 0 or not faces:
        return []

    try:
        import face_recognition
    except ImportError as exc:
        raise RuntimeError("face_recognition 未安装，请先执行 pip install face-recognition") from exc

    h, w = image_bgr.shape[:2]
    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    embeddings: List[Dict] = []
    for f in faces:
        b = f.get("box", {})
        x1, y1, x2, y2 = int(b.get("x1", 0)), int(b.get("y1", 0)), int(b.get("x2", 0)), int(b.get("y2", 0))
        ex1, ey1, ex2, ey2 = _expand_and_clip_box(x1, y1, x2, y2, w, h, margin_ratio)
        # face_recognition 需要 (top, right, bottom, left)
        location = (ey1, ex2, ey2, ex1)
        encodings = face_recognition.face_encodings(image_rgb, known_face_locations=[location])
        if not encodings:
            continue
        embeddings.append(
            {
                "embedding": encodings[0].tolist(),
                "box": {"x1": ex1, "y1": ey1, "x2": ex2, "y2": ey2, "width": ex2 - ex1, "height": ey2 - ey1},
                "score": f.get("score", 0.0),
            }
        )

    return embeddings


