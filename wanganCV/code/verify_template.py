"""
验证模板质量脚本

比较聚合模板与原始 embedding 的相似度，验证聚合效果
"""
import os
import sys
import numpy as np
from pathlib import Path
from typing import List, Dict

# Ensure package root is importable when executed as a script
if __package__ is None or __package__ == "":
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))

try:
    from .template_aggregator import load_user_embeddings
except Exception:
    try:
        from app.template_aggregator import load_user_embeddings
    except Exception:
        from template_aggregator import load_user_embeddings


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """计算两个向量的余弦相似度"""
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def verify_template(
    user_id: str,
    template_path: str,
    user_emb_dir: str,
    use_normalized: bool = True,
) -> Dict:
    """
    验证模板质量

    Args:
        user_id: 用户 ID
        template_path: 模板文件路径
        user_emb_dir: 用户 embedding 目录
        use_normalized: 是否使用归一化版本

    Returns:
        验证结果字典
    """
    result = {
        'user_id': user_id,
        'template_path': template_path,
        'num_embeddings': 0,
        'similarities': [],
        'mean_similarity': 0.0,
        'min_similarity': 0.0,
        'max_similarity': 0.0,
        'std_similarity': 0.0,
    }

    try:
        # 加载模板
        template = np.load(template_path, allow_pickle=False).astype(np.float32)
        if template.ndim != 1:
            raise ValueError(f"模板维度错误: 期望 1D, 实际 {template.ndim}D")

        # 加载所有原始 embedding
        embeddings = load_user_embeddings(user_emb_dir, use_normalized=use_normalized)
        if not embeddings:
            print(f"警告: 用户 {user_id} 没有找到 embedding")
            return result

        result['num_embeddings'] = len(embeddings)

        # 计算每个 embedding 与模板的相似度
        similarities = []
        for i, emb in enumerate(embeddings):
            sim = cosine_similarity(template, emb)
            similarities.append(float(sim))

        result['similarities'] = similarities
        result['mean_similarity'] = float(np.mean(similarities))
        result['min_similarity'] = float(np.min(similarities))
        result['max_similarity'] = float(np.max(similarities))
        result['std_similarity'] = float(np.std(similarities))

        print(f"\n用户 {user_id}:")
        print(f"  Embedding 数量: {len(embeddings)}")
        print(f"  与模板相似度:")
        print(f"    平均: {result['mean_similarity']:.4f}")
        print(f"    最小: {result['min_similarity']:.4f}")
        print(f"    最大: {result['max_similarity']:.4f}")
        print(f"    标准差: {result['std_similarity']:.4f}")

    except Exception as e:
        print(f"错误: 验证用户 {user_id} 模板时发生异常 - {str(e)}")
        result['error'] = str(e)

    return result


def verify_templates_batch(
    templates_dir: str = "data/templates/templates",
    embs_base_dir: str = "data/templates/embs",
    use_normalized: bool = True,
) -> List[Dict]:
    """
    批量验证所有模板

    Args:
        templates_dir: 模板目录
        embs_base_dir: embedding 基础目录
        use_normalized: 是否使用归一化版本

    Returns:
        验证结果列表
    """
    results = []

    if not os.path.isdir(templates_dir):
        print(f"错误: 模板目录不存在 - {templates_dir}")
        return results

    # 查找所有模板文件
    template_files = list(Path(templates_dir).glob("template_*.npy"))
    template_files.sort()

    print(f"找到 {len(template_files)} 个模板，开始验证...")

    for template_file in template_files:
        # 从文件名提取 user_id: template_user_001.npy -> user_001
        user_id = template_file.stem.replace("template_", "")
        template_path = str(template_file)
        user_emb_dir = os.path.join(embs_base_dir, user_id)

        result = verify_template(
            user_id=user_id,
            template_path=template_path,
            user_emb_dir=user_emb_dir,
            use_normalized=use_normalized,
        )
        results.append(result)

    # 汇总统计
    if results:
        all_mean_sims = [r['mean_similarity'] for r in results if 'mean_similarity' in r and r['mean_similarity'] > 0]
        if all_mean_sims:
            print(f"\n汇总统计:")
            print(f"  平均相似度: {np.mean(all_mean_sims):.4f}")
            print(f"  最小相似度: {np.min(all_mean_sims):.4f}")
            print(f"  最大相似度: {np.max(all_mean_sims):.4f}")

    return results


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='验证模板质量')
    parser.add_argument(
        '--templates-dir',
        default='data/templates/templates',
        help='模板目录（默认: data/templates/templates）'
    )
    parser.add_argument(
        '--embs-dir',
        default='data/templates/embs',
        help='embedding 基础目录（默认: data/templates/embs）'
    )
    parser.add_argument(
        '--use-raw',
        action='store_true',
        help='使用原始 embedding（默认使用归一化版本）'
    )

    args = parser.parse_args()

    results = verify_templates_batch(
        templates_dir=args.templates_dir,
        embs_base_dir=args.embs_dir,
        use_normalized=not args.use_raw,
    )

    sys.exit(0 if results else 1)
