"""
批量提取 embedding 脚本

从 manifest_enroll.csv 读取 qc_status=ok 的记录，为每张图片提取 embedding
并保存原始和归一化两份，同时记录到 emb_index.csv
"""
import os
import sys
import csv
import numpy as np
import cv2
from pathlib import Path
from datetime import datetime
from typing import List, Dict

# Ensure package root is importable when executed as a script
if __package__ is None or __package__ == "":
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))

try:
    # package execution (recommended): `python -m app.extract_embeddings ...`
    from .face_detector import DnnFaceDetector, compute_embeddings
except Exception:
    try:
        # script execution with sys.path adjusted
        from app.face_detector import DnnFaceDetector, compute_embeddings
    except Exception:
        # final fallback if current dir is app/
        from face_detector import DnnFaceDetector, compute_embeddings


def l2_normalize(embedding: np.ndarray) -> np.ndarray:
    """L2 归一化 embedding"""
    norm = np.linalg.norm(embedding)
    if norm == 0:
        return embedding
    return embedding / norm


def extract_embeddings_batch(
    manifest_enroll_path: str,
    output_base_dir: str = "data/templates",
    emb_index_path: str = "data/templates/emb_index.csv",
    margin_ratio: float = 0.2,
) -> Dict[str, int]:
    """
    批量提取 embedding

    Args:
        manifest_enroll_path: manifest_enroll.csv 文件路径
        output_base_dir: 输出根目录
        emb_index_path: embedding 索引文件路径
        margin_ratio: 裁剪时使用的 margin 比例（与检测时保持一致）

    Returns:
        统计信息字典：{'processed': 处理数量, 'success': 成功数量, 'failed': 失败数量}
    """
    # 确保目录存在
    emb_dir = os.path.join(output_base_dir, "embs")
    os.makedirs(emb_dir, exist_ok=True)
    os.makedirs(os.path.dirname(emb_index_path), exist_ok=True)

    # 读取 manifest_enroll.csv
    enroll_records: List[Dict] = []
    if os.path.exists(manifest_enroll_path):
        with open(manifest_enroll_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('qc_status', '').lower() == 'ok':
                    enroll_records.append(row)
    else:
        print(f"警告: {manifest_enroll_path} 不存在")
        return {'processed': 0, 'success': 0, 'failed': 0}

    # 读取或创建 emb_index.csv
    existing_index: Dict[str, Dict] = {}  # key: (user_id, source_file)
    index_file_exists = os.path.exists(emb_index_path)
    if index_file_exists:
        with open(emb_index_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = (row['user_id'], row['source_file'])
                existing_index[key] = row

    # 初始化检测器
    detector = DnnFaceDetector(conf_threshold=0.5)

    # 处理每条记录
    stats = {'processed': 0, 'success': 0, 'failed': 0}
    new_index_records: List[Dict] = []

    for record in enroll_records:
        stats['processed'] += 1
        user_id = record.get('user_id', '').strip()
        filepath = record.get('filepath', '').strip()
        timestamp = record.get('timestamp', '').strip()

        if not user_id or not filepath:
            print(f"警告: 跳过无效记录 - user_id={user_id}, filepath={filepath}")
            stats['failed'] += 1
            continue

        # 检查是否已处理过
        key = (user_id, filepath)
        if key in existing_index:
            print(f"跳过已处理: {user_id} - {filepath}")
            new_index_records.append(existing_index[key])
            stats['success'] += 1
            continue

        # 检查源文件是否存在
        if not os.path.exists(filepath):
            print(f"错误: 源文件不存在 - {filepath}")
            stats['failed'] += 1
            continue

        try:
            # 读取图片
            image_bgr = cv2.imread(filepath)
            if image_bgr is None:
                print(f"错误: 无法读取图片 - {filepath}")
                stats['failed'] += 1
                continue

            # 检测人脸
            faces = detector.detect(image_bgr)
            if not faces:
                print(f"警告: 未检测到人脸 - {filepath}")
                stats['failed'] += 1
                continue

            # 计算 embedding（使用置信度最高的人脸）
            embeddings_result = compute_embeddings(image_bgr, faces, margin_ratio=margin_ratio)
            if not embeddings_result:
                print(f"警告: 无法计算 embedding - {filepath}")
                stats['failed'] += 1
                continue

            embedding = np.array(embeddings_result[0]['embedding'], dtype=np.float32)
            embedding_normed = l2_normalize(embedding)

            # 创建用户目录
            user_emb_dir = os.path.join(emb_dir, user_id)
            os.makedirs(user_emb_dir, exist_ok=True)

            # 确定下一个序号
            existing_files = list(Path(user_emb_dir).glob('emb_*.npy'))
            if existing_files:
                # 提取最大序号
                max_num = 0
                for f in existing_files:
                    try:
                        num_str = f.stem.split('_')[1]  # emb_XXXX
                        max_num = max(max_num, int(num_str))
                    except (ValueError, IndexError):
                        pass
                next_num = max_num + 1
            else:
                next_num = 1

            emb_filename = f"emb_{next_num:04d}.npy"
            emb_path_raw = os.path.join(user_emb_dir, emb_filename.replace('.npy', '_raw.npy'))
            emb_path_norm = os.path.join(user_emb_dir, emb_filename.replace('.npy', '_norm.npy'))

            # 保存原始和归一化 embedding
            np.save(emb_path_raw, embedding)
            np.save(emb_path_norm, embedding_normed)

            # 记录索引（使用归一化版本的路径作为主路径）
            emb_path_relative = os.path.relpath(emb_path_norm, start=os.getcwd())
            if not timestamp:
                timestamp = datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')

            new_index_records.append({
                'user_id': user_id,
                'emb_path': emb_path_relative,
                'source_file': filepath,
                'ts': timestamp,
                'dim': str(len(embedding)),
                'normed': 'True',
            })

            print(f"成功: {user_id} - {filepath} -> {emb_path_norm}")
            stats['success'] += 1

        except Exception as e:
            print(f"错误: 处理 {filepath} 时发生异常 - {str(e)}")
            stats['failed'] += 1
            continue

    # 合并并保存 emb_index.csv
    all_records = []
    if index_file_exists:
        # 保留不在新记录中的现有记录
        for key, row in existing_index.items():
            if key not in [(r['user_id'], r['source_file']) for r in new_index_records]:
                all_records.append(row)

    all_records.extend(new_index_records)

    # 按 user_id 和 ts 排序
    all_records.sort(key=lambda x: (x.get('user_id', ''), x.get('ts', '')))

    # 写入文件
    if all_records:
        with open(emb_index_path, 'w', encoding='utf-8', newline='') as f:
            fieldnames = ['user_id', 'emb_path', 'source_file', 'ts', 'dim', 'normed']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_records)

    print(f"\n处理完成: 总计={stats['processed']}, 成功={stats['success']}, 失败={stats['failed']}")
    return stats


if __name__ == '__main__':
    import sys
    import argparse

    parser = argparse.ArgumentParser(description='批量提取 embedding')
    parser.add_argument(
        '--manifest',
        default='data/templates/manifest_enroll.csv',
        help='manifest_enroll.csv 文件路径'
    )
    parser.add_argument(
        '--output',
        default='data/templates',
        help='输出根目录'
    )
    parser.add_argument(
        '--index',
        default='data/templates/emb_index.csv',
        help='embedding 索引文件路径'
    )
    parser.add_argument(
        '--margin',
        type=float,
        default=0.2,
        help='裁剪 margin 比例（默认 0.2）'
    )

    args = parser.parse_args()

    stats = extract_embeddings_batch(
        manifest_enroll_path=args.manifest,
        output_base_dir=args.output,
        emb_index_path=args.index,
        margin_ratio=args.margin,
    )

    sys.exit(0 if stats['failed'] == 0 else 1)
