"""
人脸识别推理性能基准脚本。

作用:
    对 recognize() 主链路做逐阶段计时, 用于报告里画:
        - 端到端单帧耗时分布 (直方图 / 箱线图)
        - 各阶段 (检测 / embedding / 比对) 占比 (堆叠柱状图)
        - FPS 估算

用法:
    cd paspberry_pi/cv/code
    # 用摄像头实时抓 100 帧
    python bench_recognize.py --source camera --frames 100
    # 用文件夹里的所有 jpg/png 循环跑
    python bench_recognize.py --source dir --path ../outputs/faces --frames 100
    # 单张图片重复跑, 观察稳定态耗时 (最纯粹的推理性能, 不含 IO/解码)
    python bench_recognize.py --source image --path test.jpg --frames 200

产出:
    ./bench_results/bench_stages.csv   每帧各阶段耗时明细 (ms)
    ./bench_results/bench_summary.csv  阶段统计 (mean/median/p95/stdev + FPS)
    控制台直接打印摘要
"""

from __future__ import annotations

import argparse
import csv
import glob
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import cv2
import numpy as np

_CURRENT_DIR = Path(__file__).resolve().parent
if str(_CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(_CURRENT_DIR))

from face_detector import DnnFaceDetector, compute_embeddings  # noqa: E402
from recognize import _get_templates, l2_normalize  # noqa: E402
from verify_template import cosine_similarity  # noqa: E402


STAGES = ["detect", "embedding", "match"]


def _now_ms() -> float:
    return time.perf_counter() * 1000.0


def _read_image_safe(path: str) -> Optional[np.ndarray]:
    try:
        data = np.fromfile(path, dtype=np.uint8)
    except OSError:
        return None
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def _iter_frames(source: str, path: Optional[str], frames: int):
    """按 source 类型产出 frames 个 BGR 帧。"""
    if source == "camera":
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            raise RuntimeError("摄像头打开失败")
        try:
            for _ in range(frames):
                ok, frame = cap.read()
                if not ok:
                    break
                yield frame
        finally:
            cap.release()
        return

    if source == "image":
        if not path or not os.path.isfile(path):
            raise RuntimeError(f"图片不存在: {path}")
        frame = _read_image_safe(path)
        if frame is None:
            raise RuntimeError(f"无法解码图片: {path}")
        for _ in range(frames):
            yield frame.copy()
        return

    if source == "dir":
        if not path or not os.path.isdir(path):
            raise RuntimeError(f"目录不存在: {path}")
        files = []
        for ext in ("*.jpg", "*.jpeg", "*.png", "*.bmp"):
            files.extend(sorted(glob.glob(os.path.join(path, ext))))
        if not files:
            raise RuntimeError(f"目录里没有图片: {path}")
        count = 0
        while count < frames:
            for fp in files:
                if count >= frames:
                    break
                frame = _read_image_safe(fp)
                if frame is None:
                    continue
                yield frame
                count += 1
        return

    raise ValueError(f"未知 source: {source}")


def _bench_one(detector: DnnFaceDetector, templates: Dict[str, np.ndarray],
               frame: np.ndarray) -> Optional[Dict[str, float]]:
    stages: Dict[str, float] = {}

    t = _now_ms()
    faces = detector.detect(frame)
    stages["detect"] = _now_ms() - t
    if not faces:
        return None

    t = _now_ms()
    emb_result = compute_embeddings(frame, [faces[0]], margin_ratio=0.2)
    stages["embedding"] = _now_ms() - t
    if not emb_result:
        return None
    embedding = l2_normalize(np.array(emb_result[0]["embedding"], dtype=np.float32))

    t = _now_ms()
    best = -1.0
    for tmpl in templates.values():
        if tmpl.shape != embedding.shape:
            continue
        sim = float(cosine_similarity(tmpl, embedding))
        if sim > best:
            best = sim
    stages["match"] = _now_ms() - t
    stages["total"] = stages["detect"] + stages["embedding"] + stages["match"]
    return stages


def _summarize(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"n": 0, "mean": 0, "median": 0, "p95": 0, "min": 0, "max": 0, "stdev": 0}
    vs = sorted(values)
    p95_idx = max(0, min(len(vs) - 1, int(round(0.95 * (len(vs) - 1)))))
    return {
        "n": len(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "p95": vs[p95_idx],
        "min": min(values),
        "max": max(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["camera", "image", "dir"], default="image")
    parser.add_argument("--path", default=None, help="image/dir 模式下的路径")
    parser.add_argument("--frames", type=int, default=100)
    parser.add_argument("--warmup", type=int, default=5, help="预热帧数, 不计入统计")
    args = parser.parse_args()

    out_dir = _CURRENT_DIR / "bench_results"
    out_dir.mkdir(parents=True, exist_ok=True)

    detector = DnnFaceDetector(conf_threshold=0.5)
    templates = _get_templates()
    if not templates:
        print("[bench] 警告: 模板库为空, 比对阶段耗时将为 0 (还是可以测检测/embedding)")

    print(
        f"[bench] source={args.source} path={args.path} frames={args.frames} "
        f"warmup={args.warmup} templates={len(templates)}"
    )

    # 预热
    warmup_iter = _iter_frames(args.source, args.path, args.warmup)
    for i, frame in enumerate(warmup_iter):
        _bench_one(detector, templates, frame)
        print(f"  warmup {i + 1}/{args.warmup}")

    # 正式跑
    runs: List[Dict[str, float]] = []
    skipped = 0
    frame_iter = _iter_frames(args.source, args.path, args.frames)
    wall_start = _now_ms()
    for i, frame in enumerate(frame_iter):
        r = _bench_one(detector, templates, frame)
        if r is None:
            skipped += 1
            continue
        runs.append(r)
        if (i + 1) % 20 == 0:
            print(f"  progress {i + 1}/{args.frames}, valid={len(runs)}, skipped={skipped}")
    wall_ms = _now_ms() - wall_start

    if not runs:
        print("[bench] 没有有效样本 (可能没检测到人脸), 退出")
        sys.exit(1)

    # 明细
    detail_path = out_dir / "bench_stages.csv"
    with detail_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["frame"] + STAGES + ["total"])
        for i, r in enumerate(runs, 1):
            writer.writerow([i] + [f"{r[s]:.3f}" for s in STAGES] + [f"{r['total']:.3f}"])

    # 汇总
    fps = len(runs) / (wall_ms / 1000.0) if wall_ms > 0 else 0.0
    summary_path = out_dir / "bench_summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["stage", "n", "mean_ms", "median_ms", "p95_ms", "min_ms", "max_ms", "stdev_ms"])
        for stage in STAGES + ["total"]:
            s = _summarize([r[stage] for r in runs])
            writer.writerow([
                stage, s["n"],
                f"{s['mean']:.3f}", f"{s['median']:.3f}", f"{s['p95']:.3f}",
                f"{s['min']:.3f}", f"{s['max']:.3f}", f"{s['stdev']:.3f}",
            ])
        writer.writerow([])
        writer.writerow(["fps_estimate", f"{fps:.2f}"])
        writer.writerow(["wall_seconds", f"{wall_ms / 1000.0:.2f}"])
        writer.writerow(["skipped_frames", skipped])

    print("\n==== 推理性能摘要 (ms) ====")
    print(f"{'stage':<12}{'mean':>10}{'median':>10}{'p95':>10}{'stdev':>10}")
    for stage in STAGES + ["total"]:
        s = _summarize([r[stage] for r in runs])
        print(f"{stage:<12}{s['mean']:>10.2f}{s['median']:>10.2f}{s['p95']:>10.2f}{s['stdev']:>10.2f}")
    print(f"\n有效样本 {len(runs)} / 总帧 {args.frames}, 跳过 {skipped}")
    print(f"墙钟耗时 {wall_ms / 1000:.2f}s, 折合 FPS ≈ {fps:.2f}")
    print(f"明细: {detail_path}")
    print(f"摘要: {summary_path}")


if __name__ == "__main__":
    main()
