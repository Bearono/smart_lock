"""
人脸识别函数

封装所有识别逻辑：人脸检测、embedding 提取、模板比对、相似度计算、阈值判断
"""
import os
import sys
import glob
import numpy as np
import cv2
from typing import Tuple, Optional, Dict

# Ensure package root is importable when executed as a script
if __package__ is None or __package__ == "":
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))

try:
    from .face_detector import DnnFaceDetector, compute_embeddings
    from .verify_template import cosine_similarity
except Exception:
    try:
        from code.face_detector import DnnFaceDetector, compute_embeddings
        from code.verify_template import cosine_similarity
    except Exception:
        from face_detector import DnnFaceDetector, compute_embeddings
        from verify_template import cosine_similarity

# 获取当前文件所在目录，并计算项目根目录和模板目录
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_CURRENT_DIR)
_DEFAULT_TEMPLATES_DIR = os.path.join(_CURRENT_DIR, "data", "templates", "templates")


# 全局变量：模板库和检测器（延迟加载）
_templates_cache: Optional[Dict[str, np.ndarray]] = None
_detector_cache: Optional[DnnFaceDetector] = None


def l2_normalize(embedding: np.ndarray) -> np.ndarray:
    """L2 归一化 embedding"""
    norm = np.linalg.norm(embedding)
    if norm == 0:
        return embedding
    return embedding / norm


def _read_image(image_path: str) -> Optional[np.ndarray]:
    """Read images safely on Windows paths containing non-ASCII characters."""
    try:
        data = np.fromfile(image_path, dtype=np.uint8)
    except OSError:
        return None
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def _load_templates(templates_dir: str = None) -> Dict[str, np.ndarray]:
    if templates_dir is None:
        templates_dir = _DEFAULT_TEMPLATES_DIR
    """
    加载所有用户模板
    
    Args:
        templates_dir: 模板文件目录
    
    Returns:
        字典，key 为 user_id，value 为归一化的模板向量
    """
    templates = {}
    
    if not os.path.isdir(templates_dir):
        return templates
    
    template_files = glob.glob(os.path.join(templates_dir, "template_*.npy"))
    
    for template_path in template_files:
        try:
            # 从文件名提取 user_id: template_user_001.npy -> user_001
            filename = os.path.basename(template_path)
            user_id = filename.replace("template_", "").replace(".npy", "")
            
            # 加载模板
            template = np.load(template_path, allow_pickle=False).astype(np.float32)
            
            # 确保是 1D 向量并归一化
            if template.ndim == 1:
                template = l2_normalize(template)
                templates[user_id] = template
        except Exception:
            continue
    
    return templates


def _get_templates(templates_dir: str = None) -> Dict[str, np.ndarray]:
    if templates_dir is None:
        templates_dir = _DEFAULT_TEMPLATES_DIR
    """获取模板库（带缓存）"""
    global _templates_cache
    if _templates_cache is None:
        _templates_cache = _load_templates(templates_dir)
    return _templates_cache


def _get_detector(conf_threshold: float = 0.5) -> DnnFaceDetector:
    """获取检测器（带缓存）"""
    global _detector_cache
    if _detector_cache is None:
        _detector_cache = DnnFaceDetector(conf_threshold=conf_threshold)
    return _detector_cache


def recognize(
    image: np.ndarray,
    templates_dir: str = None,
    conf_threshold: float = 0.5,
    margin_ratio: float = 0.2,
    match_threshold: float = 0.65,
) -> Tuple[Optional[str], float]:
    if templates_dir is None:
        templates_dir = _DEFAULT_TEMPLATES_DIR
    """
    人脸识别函数
    
    完整流程：
    1. 人脸检测
    2. 提取 embedding
    3. 与模板库中所有模板计算余弦相似度
    4. 取相似度最高的模板作为候选身份
    5. 根据阈值判断是否通过身份认证
    
    Args:
        image: BGR 格式的图像数组（numpy array）
        templates_dir: 模板文件目录
        conf_threshold: 人脸检测置信度阈值
        margin_ratio: 裁剪时的 margin 比例
        match_threshold: 身份匹配阈值（余弦相似度，0-1）
    
    Returns:
        (user_id, confidence)
        - user_id: 识别到的用户 ID，如果未匹配则返回 None
        - confidence: 相似度分数 (0-1)，如果未匹配则返回最高相似度
    
    示例:
        import cv2
        image = cv2.imread("test.jpg")
        user_id, conf = recognize(image)
        if user_id:
            print(f"识别成功: {user_id}, 相似度: {conf:.4f}")
        else:
            print(f"识别失败，最高相似度: {conf:.4f}")
    """
    # 1. 加载模板库
    templates = _get_templates(templates_dir)
    if not templates:
        return None, 0.0
    
    # 2. 人脸检测
    detector = _get_detector(conf_threshold)
    faces = detector.detect(image)
    if not faces:
        return None, 0.0
    
    # 使用置信度最高的人脸
    best_face = faces[0]
    
    # 3. 提取 embedding
    embeddings_result = compute_embeddings(
        image,
        [best_face],
        margin_ratio=margin_ratio
    )
    
    if not embeddings_result:
        return None, 0.0
    
    # 提取并归一化 embedding
    embedding = np.array(embeddings_result[0]['embedding'], dtype=np.float32)
    embedding = l2_normalize(embedding)
    
    # 4. 与所有模板比对，计算余弦相似度
    best_user_id = None
    best_similarity = -1.0
    
    for user_id, template in templates.items():
        if template.shape != embedding.shape:
            continue
        
        similarity = float(cosine_similarity(template, embedding))
        
        if similarity > best_similarity:
            best_similarity = similarity
            best_user_id = user_id
    
    # 5. 根据阈值判断是否通过身份认证
    if best_similarity >= match_threshold:
        return best_user_id, best_similarity
    else:
        return None, best_similarity


def recognize_from_path(
    image_path: str,
    templates_dir: str = None,
    conf_threshold: float = 0.5,
    margin_ratio: float = 0.2,
    match_threshold: float = 0.65,
) -> Tuple[Optional[str], float]:
    if templates_dir is None:
        templates_dir = _DEFAULT_TEMPLATES_DIR
    """
    从图片文件路径进行识别
    
    Args:
        image_path: 图片文件路径
        templates_dir: 模板文件目录
        conf_threshold: 人脸检测置信度阈值
        margin_ratio: 裁剪时的 margin 比例
        match_threshold: 身份匹配阈值（余弦相似度）
    
    Returns:
        (user_id, confidence)
    """
    image = _read_image(image_path)
    if image is None:
        return None, 0.0
    
    return recognize(
        image,
        templates_dir=templates_dir,
        conf_threshold=conf_threshold,
        margin_ratio=margin_ratio,
        match_threshold=match_threshold,
    )


def reload_templates(templates_dir: str = None):
    """重新加载模板库（当模板文件更新后调用）"""
    global _templates_cache
    if templates_dir is None:
        templates_dir = _DEFAULT_TEMPLATES_DIR
    _templates_cache = None
    _get_templates(templates_dir)  # 触发重新加载
