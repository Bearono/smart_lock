"""人脸模板录入脚本

交互式采集若干张正面人脸 → 检测 → 提取 embedding → L2 归一化 → 聚合成模板
→ 保存为 template_<user_id>.npy。

用法（在 paspberry_pi/cv/code 目录下）：
    python enroll_face.py --user bearono
    # 默认采集 8 张样本；按 SPACE 拍当前帧，q 提前退出。

无显示器场景（树莓派 SSH）：
    python enroll_face.py --user bearono --headless --samples 8 --interval 0.6

录入完成后会保存到：
    data/templates/templates/template_<user_id>.npy

注意：app.py / recognize.py 中 _templates_cache 是进程内缓存，
新模板生效需要重启树莓派网关 (app.py)。
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

_CURRENT_DIR = Path(__file__).resolve().parent
if str(_CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(_CURRENT_DIR))

from face_detector import DnnFaceDetector, compute_embeddings  # noqa: E402

_DEFAULT_TEMPLATES_DIR = _CURRENT_DIR / "data" / "templates" / "templates"
_DEFAULT_EMBS_DIR = _CURRENT_DIR / "data" / "templates" / "embs"


class _OpenCvCamera:
    def __init__(self, camera_index: int):
        self.cap = cv2.VideoCapture(camera_index)
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open camera index {camera_index}")

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        return self.cap.read()

    def release(self) -> None:
        self.cap.release()


class _Picamera2Camera:
    def __init__(self):
        try:
            from picamera2 import Picamera2
        except ImportError as exc:
            raise RuntimeError(
                "Picamera2 is not installed. Install it with: sudo apt install python3-picamera2"
            ) from exc

        self.camera = Picamera2()
        config = self.camera.create_preview_configuration(
            main={"format": "RGB888", "size": (640, 480)}
        )
        self.camera.configure(config)
        self.camera.start()
        time.sleep(1.0)

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        frame_rgb = self.camera.capture_array()
        if frame_rgb is None:
            return False, None
        return True, cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

    def release(self) -> None:
        self.camera.stop()


def _open_camera(camera_index: int, backend: str):
    if backend == "picamera2":
        return _Picamera2Camera()
    if backend == "opencv":
        return _OpenCvCamera(camera_index)

    try:
        return _Picamera2Camera()
    except Exception as picam_exc:
        try:
            return _OpenCvCamera(camera_index)
        except Exception as opencv_exc:
            raise RuntimeError(
                "Cannot open camera with picamera2 or OpenCV. "
                f"picamera2 error: {picam_exc}; opencv error: {opencv_exc}"
            ) from opencv_exc


def _l2_normalize(v: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(v)
    if norm == 0:
        return v
    return v / norm


def _extract_one(detector: DnnFaceDetector, frame: np.ndarray) -> Optional[np.ndarray]:
    """单帧 → 最大置信度人脸 → 归一化 embedding，失败返回 None。"""
    faces = detector.detect(frame)
    if not faces:
        return None
    best = faces[0]
    result = compute_embeddings(frame, [best], margin_ratio=0.2)
    if not result:
        return None
    emb = np.asarray(result[0]["embedding"], dtype=np.float32)
    return _l2_normalize(emb)


def _draw_overlay(frame: np.ndarray, msg: str, collected: int, target: int) -> np.ndarray:
    canvas = frame.copy()
    text = f"{msg}  [{collected}/{target}]  SPACE=capture  q=quit"
    cv2.putText(canvas, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    return canvas


def collect_with_preview(camera_index: int, samples: int, detector: DnnFaceDetector, backend: str) -> List[np.ndarray]:
    """带预览窗口：用户按空格捕获，每次只取检测到人脸的帧。"""
    cap = _open_camera(camera_index, backend)

    collected: List[np.ndarray] = []
    try:
        while len(collected) < samples:
            ret, frame = cap.read()
            if not ret:
                continue
            msg = "Press SPACE to capture" if len(collected) < samples else "Done"
            cv2.imshow("Face Enroll", _draw_overlay(frame, msg, len(collected), samples))
            key = cv2.waitKey(20) & 0xFF
            if key == ord("q"):
                break
            if key == 32:
                emb = _extract_one(detector, frame)
                if emb is None:
                    print("  - no face detected in this frame, retry")
                    continue
                collected.append(emb)
                print(f"  + captured sample {len(collected)}/{samples}")
    finally:
        cap.release()
        cv2.destroyAllWindows()
    return collected


def collect_headless(
    camera_index: int,
    samples: int,
    interval: float,
    detector: DnnFaceDetector,
    backend: str,
) -> List[np.ndarray]:
    """无窗口：固定间隔自动抓帧，跳过未检测到人脸的帧。"""
    cap = _open_camera(camera_index, backend)

    collected: List[np.ndarray] = []
    max_attempts = samples * 6
    attempts = 0
    try:
        print(f"Headless mode: capture every {interval}s, target {samples} samples")
        while len(collected) < samples and attempts < max_attempts:
            attempts += 1
            ret, frame = cap.read()
            if not ret:
                time.sleep(interval)
                continue
            emb = _extract_one(detector, frame)
            if emb is None:
                print(f"  attempt {attempts}: no face")
            else:
                collected.append(emb)
                print(f"  + captured sample {len(collected)}/{samples}")
            time.sleep(interval)
    finally:
        cap.release()
    return collected


def save_template(user_id: str, embeddings: List[np.ndarray], templates_dir: Path, embs_dir: Path) -> Path:
    if not embeddings:
        raise RuntimeError("No embeddings captured, cannot build template")

    user_emb_dir = embs_dir / user_id
    user_emb_dir.mkdir(parents=True, exist_ok=True)
    for idx, emb in enumerate(embeddings, start=1):
        np.save(user_emb_dir / f"emb_{idx:04d}_norm.npy", emb)

    template = np.mean(np.stack(embeddings, axis=0), axis=0)
    template = _l2_normalize(template).astype(np.float32)

    templates_dir.mkdir(parents=True, exist_ok=True)
    template_path = templates_dir / f"template_{user_id}.npy"
    np.save(template_path, template)
    return template_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Enroll a new face template")
    parser.add_argument("--user", required=True, help="user_id, e.g. bearono — must match the backend username")
    parser.add_argument("--samples", type=int, default=8, help="number of samples to aggregate (default 8)")
    parser.add_argument("--camera", type=int, default=0, help="camera index (default 0)")
    parser.add_argument(
        "--backend",
        choices=("auto", "picamera2", "opencv"),
        default="auto",
        help="camera backend: auto, picamera2, or opencv (default auto)",
    )
    parser.add_argument("--headless", action="store_true", help="no preview window, auto-capture")
    parser.add_argument("--interval", type=float, default=0.6, help="seconds between auto-captures in headless mode")
    parser.add_argument(
        "--templates-dir",
        default=str(_DEFAULT_TEMPLATES_DIR),
        help="output dir for template .npy files",
    )
    parser.add_argument(
        "--embs-dir",
        default=str(_DEFAULT_EMBS_DIR),
        help="output dir for per-sample embeddings",
    )
    args = parser.parse_args()

    print(f"Enrolling user: {args.user}")
    detector = DnnFaceDetector(conf_threshold=0.5)

    if args.headless:
        embeddings = collect_headless(args.camera, args.samples, args.interval, detector, args.backend)
    else:
        embeddings = collect_with_preview(args.camera, args.samples, detector, args.backend)

    if not embeddings:
        print("No samples collected. Aborting.")
        return 1

    template_path = save_template(
        args.user,
        embeddings,
        Path(args.templates_dir),
        Path(args.embs_dir),
    )
    similarities = [float(np.dot(emb, np.load(template_path))) for emb in embeddings]
    print(f"Saved template: {template_path}")
    print(f"Captured {len(embeddings)} samples")
    print(f"Self-similarity mean={np.mean(similarities):.4f} min={np.min(similarities):.4f}")
    print("Restart the Pi gateway (app.py) to pick up the new template.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
