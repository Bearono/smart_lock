"""
Embedding 聚合功能使用示例
"""
import numpy as np
from app.template_aggregator import (
    load_user_embeddings,
    aggregate_embeddings,
    create_user_template,
    create_templates_batch,
)
from app.verify_template import verify_template, cosine_similarity


def example_single_user():
    """示例：为单个用户创建模板"""
    print("=" * 60)
    print("示例 1: 为单个用户创建模板")
    print("=" * 60)

    user_id = "user_001"
    user_emb_dir = "data/templates/embs/user_001"
    output_dir = "data/templates/templates"

    # 方法 1: 使用高级函数直接创建
    result = create_user_template(
        user_id=user_id,
        user_emb_dir=user_emb_dir,
        output_dir=output_dir,
        method="mean",
        use_normalized=True,
    )

    if result['success']:
        print(f"[成功] 模板创建成功: {result['template_path']}")
        print(f"  - 使用了 {result['num_embeddings']} 个 embedding")
        print(f"  - 维度: {result['dim']}")
        print(f"  - 方法: {result['method']}")


def example_custom_aggregation():
    """示例：自定义聚合过程"""
    print("\n" + "=" * 60)
    print("示例 2: 自定义聚合过程")
    print("=" * 60)

    user_emb_dir = "data/templates/embs/user_001"

    # 加载所有 embedding
    embeddings = load_user_embeddings(user_emb_dir, use_normalized=True)
    print(f"加载了 {len(embeddings)} 个 embedding")

    # 使用不同方法聚合
    methods = ["mean", "median"]
    for method in methods:
        template = aggregate_embeddings(embeddings, method=method)
        print(f"\n{method} 方法:")
        print(f"  - 模板维度: {template.shape}")
        print(f"  - L2 范数: {np.linalg.norm(template):.6f}")

        # 计算与原始 embedding 的平均相似度
        similarities = [cosine_similarity(template, emb) for emb in embeddings]
        print(f"  - 平均相似度: {np.mean(similarities):.4f}")


def example_batch_processing():
    """示例：批量处理所有用户"""
    print("\n" + "=" * 60)
    print("示例 3: 批量处理所有用户")
    print("=" * 60)

    stats = create_templates_batch(
        embs_base_dir="data/templates/embs",
        templates_output_dir="data/templates/templates",
        method="mean",
        use_normalized=True,
    )

    print(f"\n处理结果:")
    print(f"  - 总用户数: {stats['total_users']}")
    print(f"  - 成功: {stats['success']}")
    print(f"  - 失败: {stats['failed']}")


def example_verify_template():
    """示例：验证模板质量"""
    print("\n" + "=" * 60)
    print("示例 4: 验证模板质量")
    print("=" * 60)

    user_id = "user_001"
    template_path = "data/templates/templates/template_user_001.npy"
    user_emb_dir = "data/templates/embs/user_001"

    result = verify_template(
        user_id=user_id,
        template_path=template_path,
        user_emb_dir=user_emb_dir,
        use_normalized=True,
    )

    if 'mean_similarity' in result:
        print(f"\n验证结果:")
        print(f"  - 平均相似度: {result['mean_similarity']:.4f}")
        print(f"  - 最小相似度: {result['min_similarity']:.4f}")
        print(f"  - 最大相似度: {result['max_similarity']:.4f}")
        print(f"  - 标准差: {result['std_similarity']:.4f}")


def example_compare_methods():
    """示例：比较不同聚合方法的效果"""
    print("\n" + "=" * 60)
    print("示例 5: 比较不同聚合方法")
    print("=" * 60)

    user_emb_dir = "data/templates/embs/user_001"
    embeddings = load_user_embeddings(user_emb_dir, use_normalized=True)

    methods = ["mean", "median"]
    results = {}

    for method in methods:
        template = aggregate_embeddings(embeddings, method=method)
        similarities = [cosine_similarity(template, emb) for emb in embeddings]
        results[method] = {
            'mean': np.mean(similarities),
            'std': np.std(similarities),
            'min': np.min(similarities),
            'max': np.max(similarities),
        }

    print("\n方法比较:")
    for method, stats in results.items():
        print(f"\n{method}:")
        print(f"  平均相似度: {stats['mean']:.4f}")
        print(f"  标准差: {stats['std']:.4f}")
        print(f"  范围: [{stats['min']:.4f}, {stats['max']:.4f}]")


if __name__ == '__main__':
    # 运行所有示例
    try:
        example_single_user()
        example_custom_aggregation()
        example_batch_processing()
        example_verify_template()
        example_compare_methods()
        print("\n" + "=" * 60)
        print("所有示例运行完成！")
        print("=" * 60)
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
