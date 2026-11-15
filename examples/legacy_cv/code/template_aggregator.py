"""
Embedding 聚合模块

将同一个用户的多张 embedding 组合成一个稳定模板，作为身份签名
"""
import os
import sys
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Literal
from datetime import datetime

# Ensure package root is importable when executed as a script
if __package__ is None or __package__ == "":
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))

try:
    from .extract_embeddings import l2_normalize
except Exception:
    try:
        from app.extract_embeddings import l2_normalize
    except Exception:
        from extract_embeddings import l2_normalize


def load_user_embeddings(
    user_emb_dir: str,
    use_normalized: bool = True,
) -> List[np.ndarray]:
    """
    加载指定用户目录下的所有 embedding

    Args:
        user_emb_dir: 用户 embedding 目录路径
        use_normalized: 是否使用归一化版本（推荐 True）

    Returns:
        embedding 列表，每个元素是一个 numpy 数组
    """
    if not os.path.isdir(user_emb_dir):
        return []

    embeddings: List[np.ndarray] = []
    pattern = "*_norm.npy" if use_normalized else "*_raw.npy"

    for emb_file in sorted(Path(user_emb_dir).glob(pattern)):
        try:
            emb = np.load(str(emb_file), allow_pickle=False)
            if emb.ndim == 1 and len(emb) > 0:
                embeddings.append(emb.astype(np.float32))
        except Exception as e:
            print(f"警告: 无法加载 {emb_file}: {e}")
            continue

    return embeddings


def aggregate_embeddings(
    embeddings: List[np.ndarray],
    method: Literal["mean", "median", "weighted_mean"] = "mean",
    weights: Optional[List[float]] = None,
) -> np.ndarray:
    """
    将多个 embedding 聚合成一个稳定模板

    Args:
        embeddings: embedding 列表，每个元素是一个 numpy 数组
        method: 聚合方法
            - "mean": 简单平均（默认，推荐）
            - "median": 中位数（对异常值更鲁棒）
            - "weighted_mean": 加权平均（需要提供 weights）
        weights: 权重列表（仅用于 weighted_mean 方法）

    Returns:
        聚合后的 embedding（已 L2 归一化）
    """
    if not embeddings:
        raise ValueError("embeddings 列表不能为空")

    if len(embeddings) == 1:
        return l2_normalize(embeddings[0].copy())

    # 确保所有 embedding 维度一致
    dim = len(embeddings[0])
    for emb in embeddings:
        if len(emb) != dim:
            raise ValueError(f"embedding 维度不一致: 期望 {dim}, 实际 {len(emb)}")

    # 转换为 numpy 数组矩阵
    emb_matrix = np.array(embeddings, dtype=np.float32)  # shape: (N, dim)

    if method == "mean":
        # 简单平均
        template = np.mean(emb_matrix, axis=0)

    elif method == "median":
        # 中位数（对异常值更鲁棒）
        template = np.median(emb_matrix, axis=0)

    elif method == "weighted_mean":
        # 加权平均
        if weights is None:
            raise ValueError("weighted_mean 方法需要提供 weights 参数")
        if len(weights) != len(embeddings):
            raise ValueError(f"weights 长度 ({len(weights)}) 与 embeddings 数量 ({len(embeddings)}) 不匹配")
        weights_array = np.array(weights, dtype=np.float32)
        weights_array = weights_array / np.sum(weights_array)  # 归一化权重
        template = np.average(emb_matrix, axis=0, weights=weights_array)

    else:
        raise ValueError(f"不支持的聚合方法: {method}")

    # L2 归一化
    template = l2_normalize(template)

    return template


def create_user_template(
    user_id: str,
    user_emb_dir: str,
    output_dir: str,
    method: Literal["mean", "median", "weighted_mean"] = "mean",
    use_normalized: bool = True,
    weights: Optional[List[float]] = None,
) -> Dict[str, any]:
    """
    为指定用户创建聚合模板

    Args:
        user_id: 用户 ID
        user_emb_dir: 用户 embedding 目录路径
        output_dir: 模板输出目录
        method: 聚合方法
        use_normalized: 是否使用归一化版本的 embedding
        weights: 权重列表（仅用于 weighted_mean 方法）

    Returns:
        包含模板信息的字典：
        {
            'user_id': str,
            'template_path': str,
            'num_embeddings': int,
            'method': str,
            'dim': int,
            'success': bool
        }
    """
    result = {
        'user_id': user_id,
        'template_path': None,
        'num_embeddings': 0,
        'method': method,
        'dim': 0,
        'success': False,
    }

    try:
        # 加载所有 embedding
        embeddings = load_user_embeddings(user_emb_dir, use_normalized=use_normalized)
        if not embeddings:
            print(f"警告: 用户 {user_id} 没有找到 embedding")
            return result

        result['num_embeddings'] = len(embeddings)
        result['dim'] = len(embeddings[0])

        # 聚合
        template = aggregate_embeddings(embeddings, method=method, weights=weights)

        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)

        # 保存模板
        template_filename = f"template_{user_id}.npy"
        template_path = os.path.join(output_dir, template_filename)
        np.save(template_path, template)

        result['template_path'] = template_path
        result['success'] = True

        print(f"成功: 用户 {user_id} - {len(embeddings)} 个 embedding -> {template_path}")

    except Exception as e:
        print(f"错误: 创建用户 {user_id} 模板时发生异常 - {str(e)}")
        result['success'] = False

    return result


def create_templates_batch(
    embs_base_dir: str = "data/templates/embs",
    templates_output_dir: str = "data/templates/templates",
    method: Literal["mean", "median", "weighted_mean"] = "mean",
    use_normalized: bool = True,
) -> Dict[str, any]:
    """
    批量为所有用户创建聚合模板

    Args:
        embs_base_dir: embedding 基础目录（包含各用户子目录）
        templates_output_dir: 模板输出目录
        method: 聚合方法
        use_normalized: 是否使用归一化版本的 embedding

    Returns:
        统计信息字典：
        {
            'total_users': int,
            'success': int,
            'failed': int,
            'results': List[Dict]
        }
    """
    stats = {
        'total_users': 0,
        'success': 0,
        'failed': 0,
        'results': [],
    }

    if not os.path.isdir(embs_base_dir):
        print(f"错误: embedding 目录不存在 - {embs_base_dir}")
        return stats

    # 查找所有用户目录
    user_dirs = [d for d in os.listdir(embs_base_dir) if os.path.isdir(os.path.join(embs_base_dir, d))]
    user_dirs.sort()

    stats['total_users'] = len(user_dirs)

    print(f"找到 {len(user_dirs)} 个用户，开始创建模板...")

    for user_id in user_dirs:
        user_emb_dir = os.path.join(embs_base_dir, user_id)
        result = create_user_template(
            user_id=user_id,
            user_emb_dir=user_emb_dir,
            output_dir=templates_output_dir,
            method=method,
            use_normalized=use_normalized,
        )
        stats['results'].append(result)
        if result['success']:
            stats['success'] += 1
        else:
            stats['failed'] += 1

    print(f"\n处理完成: 总计={stats['total_users']}, 成功={stats['success']}, 失败={stats['failed']}")
    return stats


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='批量创建用户身份模板')
    parser.add_argument(
        '--embs-dir',
        default='data/templates/embs',
        help='embedding 基础目录（默认: data/templates/embs）'
    )
    parser.add_argument(
        '--output',
        default='data/templates/templates',
        help='模板输出目录（默认: data/templates/templates）'
    )
    parser.add_argument(
        '--method',
        choices=['mean', 'median', 'weighted_mean'],
        default='mean',
        help='聚合方法（默认: mean）'
    )
    parser.add_argument(
        '--use-raw',
        action='store_true',
        help='使用原始 embedding（默认使用归一化版本）'
    )

    args = parser.parse_args()

    stats = create_templates_batch(
        embs_base_dir=args.embs_dir,
        templates_output_dir=args.output,
        method=args.method,
        use_normalized=not args.use_raw,
    )

    sys.exit(0 if stats['failed'] == 0 else 1)
