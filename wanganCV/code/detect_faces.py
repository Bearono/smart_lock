"""
人脸检测命令行工具

直接运行脚本进行人脸检测，无需启动 API 服务器
"""
import os
import sys
import json
import argparse
import cv2
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

# Ensure package root is importable when executed as a script
if __package__ is None or __package__ == "":
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))

try:
    # package execution (recommended): `python -m app.detect_faces ...`
    from .face_detector import DnnFaceDetector, crop_and_save_faces, compute_embeddings
except Exception:
    try:
        # script execution with sys.path adjusted
        from app.face_detector import DnnFaceDetector, crop_and_save_faces, compute_embeddings
    except Exception:
        # final fallback if current dir is app/
        from face_detector import DnnFaceDetector, crop_and_save_faces, compute_embeddings


def detect_faces_from_file(
    image_path: str,
    conf_threshold: float = 0.5,
    save_crops: bool = False,
    output_dir: str = "outputs/faces",
    margin_ratio: float = 0.2,
    return_embeddings: bool = False,
    output_json: Optional[str] = None,
) -> Dict:
    """
    从图片文件检测人脸

    Args:
        image_path: 图片文件路径
        conf_threshold: 置信度阈值
        save_crops: 是否保存裁剪的人脸
        output_dir: 输出目录
        margin_ratio: 裁剪时的 margin 比例
        return_embeddings: 是否返回 embedding
        output_json: 输出 JSON 文件路径（可选）

    Returns:
        检测结果字典
    """
    # 检查文件是否存在
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"图片文件不存在: {image_path}")

    # 读取图片
    image_bgr = cv2.imread(image_path)
    if image_bgr is None:
        raise ValueError(f"无法读取图片文件: {image_path}")

    # 初始化检测器
    detector = DnnFaceDetector(conf_threshold=conf_threshold)
    faces = detector.detect(image_bgr)

    # 保存裁剪的人脸
    saved = []
    if save_crops and len(faces) > 0:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        saved = crop_and_save_faces(
            image_bgr,
            faces,
            output_dir=output_dir,
            filename_prefix=f"faces_{ts}",
            margin_ratio=margin_ratio,
        )

    # 计算 embedding
    embeddings = []
    if return_embeddings and len(faces) > 0:
        embeddings = compute_embeddings(image_bgr, faces, margin_ratio=margin_ratio)
        if save_crops and embeddings:
            for idx, emb in enumerate(embeddings):
                if idx < len(saved):
                    saved[idx]["embedding"] = emb.get("embedding")

    h, w = image_bgr.shape[:2]
    result = {
        "image": {"width": w, "height": h},
        "num_faces": len(faces),
        "faces": faces,
        "saved": saved,
        "embeddings": embeddings,
    }

    # 保存 JSON 结果
    if output_json:
        os.makedirs(os.path.dirname(output_json) if os.path.dirname(output_json) else ".", exist_ok=True)
        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"结果已保存到: {output_json}")

    return result


def print_result(result: Dict, verbose: bool = True):
    """打印检测结果"""
    print(f"\n图片尺寸: {result['image']['width']} x {result['image']['height']}")
    print(f"检测到人脸数量: {result['num_faces']}")

    if result['num_faces'] > 0:
        print("\n人脸信息:")
        for i, face in enumerate(result['faces'], 1):
            box = face['box']
            print(f"  人脸 {i}:")
            print(f"    位置: ({box['x1']}, {box['y1']}) -> ({box['x2']}, {box['y2']})")
            print(f"    尺寸: {box['width']} x {box['height']}")
            print(f"    置信度: {face['score']:.4f}")

        if result.get('saved'):
            print("\n保存的裁剪图片:")
            for i, saved_info in enumerate(result['saved'], 1):
                print(f"  人脸 {i}: {saved_info['file']}")

        if result.get('embeddings'):
            print(f"\nEmbedding 数量: {len(result['embeddings'])}")
            if verbose:
                for i, emb_info in enumerate(result['embeddings'], 1):
                    emb = emb_info.get('embedding', [])
                    if emb:
                        print(f"  人脸 {i} embedding 维度: {len(emb)}")
    else:
        print("未检测到人脸")


def main():
    parser = argparse.ArgumentParser(
        description='人脸检测工具 - 直接运行，无需启动 API 服务器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
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
        """
    )

    parser.add_argument(
        'image',
        help='图片文件路径'
    )
    parser.add_argument(
        '--conf-threshold',
        type=float,
        default=0.5,
        help='置信度阈值（默认: 0.5）'
    )
    parser.add_argument(
        '--save-crops',
        action='store_true',
        help='保存裁剪的人脸图片'
    )
    parser.add_argument(
        '--output-dir',
        default='outputs/faces',
        help='裁剪图片输出目录（默认: outputs/faces）'
    )
    parser.add_argument(
        '--margin-ratio',
        type=float,
        default=0.2,
        help='裁剪时的 margin 比例（默认: 0.2）'
    )
    parser.add_argument(
        '--embeddings',
        action='store_true',
        help='计算并返回 embedding'
    )
    parser.add_argument(
        '--output-json',
        help='将结果保存为 JSON 文件（可选）'
    )
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='静默模式，只输出 JSON（如果指定了 --output-json）'
    )

    args = parser.parse_args()

    try:
        # 执行检测
        result = detect_faces_from_file(
            image_path=args.image,
            conf_threshold=args.conf_threshold,
            save_crops=args.save_crops,
            output_dir=args.output_dir,
            margin_ratio=args.margin_ratio,
            return_embeddings=args.embeddings,
            output_json=args.output_json,
        )

        # 打印结果
        if not args.quiet:
            print_result(result, verbose=True)
        elif args.output_json:
            print(f"检测完成，结果已保存到: {args.output_json}")

        # 如果只输出 JSON，打印到标准输出
        if args.quiet and not args.output_json:
            print(json.dumps(result, ensure_ascii=False, indent=2))

    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
