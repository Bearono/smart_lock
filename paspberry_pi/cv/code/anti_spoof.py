"""Pinned MiniFASNetV2 passive PAD. Fail closed; scores are not proof of life.

Model: Minivision Silent-Face-Anti-Spoofing, Apache-2.0. Export/provenance
is verified by deploy/export_pad.py. Operating threshold needs local evaluation.
"""
import hashlib
from pathlib import Path
import cv2
import numpy as np
try:
    from .paths import models_dir
    from .resource_guard import serialized_inference
except ImportError:
    from paths import models_dir
    from resource_guard import serialized_inference

MODEL_SHA256 = 'b5156dece1bdc64a6806d037a783a2e3db178fb054aa71c6518992de68d5b841'
_network = None
_model_path = None


def verify_pad_model(directory=None):
    path = Path(directory or models_dir()) / 'minifasnet-v2.onnx'
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('Missing or invalid PAD model')
    if hashlib.sha256(path.read_bytes()).hexdigest() != MODEL_SHA256:
        raise ValueError('PAD model checksum mismatch')
    return path


def crop_patch(image, box):
    if not isinstance(image, np.ndarray) or image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError('Expected BGR uint8 image')
    h, w = image.shape[:2]
    x, y, right, bottom = (box[k] for k in ('x1', 'y1', 'x2', 'y2'))
    if not all(type(v) is int for v in (x, y, right, bottom)) or not 0 <= x < right < w or not 0 <= y < bottom < h:
        raise ValueError('Invalid face box')
    bw, bh = right - x, bottom - y
    scale = min(2.7, (w - 1) / bw, (h - 1) / bh)
    new_w, new_h = bw * scale, bh * scale
    left = min(max(x + bw / 2 - new_w / 2, 0), w - 1 - new_w)
    top = min(max(y + bh / 2 - new_h / 2, 0), h - 1 - new_h)
    patch = image[int(top):int(top + new_h)+1, int(left):int(left + new_w)+1]
    return cv2.resize(patch, (80, 80), interpolation=cv2.INTER_LINEAR)


@serialized_inference
def score_frame(image, detector):
    global _network, _model_path
    faces = detector.detect(image)
    if len(faces) != 1:
        return 0.0
    path = verify_pad_model()
    if _network is None or _model_path != str(path):
        _network = cv2.dnn.readNetFromONNX(str(path))
        _model_path = str(path)
    patch = crop_patch(image, faces[0]['box'])
    _network.setInput(cv2.dnn.blobFromImage(patch, scalefactor=1.0, swapRB=False, crop=False))
    logits = np.asarray(_network.forward(), dtype=np.float64).reshape(-1)
    if len(logits) != 3 or not np.all(np.isfinite(logits)):
        raise ValueError('Invalid PAD model result')
    probabilities = np.exp(logits - np.max(logits))
    return float(probabilities[1] / np.sum(probabilities))
