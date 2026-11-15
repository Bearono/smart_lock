"""Pinned MiniFASNetV2 passive PAD. Fail closed; scores are not proof of life.

Model: Minivision Silent-Face-Anti-Spoofing, Apache-2.0. Export/provenance
is verified by deploy/export_pad.py. Operating threshold needs local evaluation.
"""
import hashlib
import math
from pathlib import Path
import cv2
import numpy as np
try:
    from .paths import models_dir
    from .resource_guard import serialized_inference
    from .model_manifest import PAD_DETECTOR_MODELS, verify_model_files
except ImportError:
    from paths import models_dir
    from resource_guard import serialized_inference
    from model_manifest import PAD_DETECTOR_MODELS, verify_model_files

MODEL_SHA256 = 'b5156dece1bdc64a6806d037a783a2e3db178fb054aa71c6518992de68d5b841'
_network = None
_model_path = None
_detector = None
_detector_path = None


def verify_pad_model(directory=None):
    path = Path(directory or models_dir()) / 'minifasnet-v2.onnx'
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('Missing or invalid PAD model')
    if hashlib.sha256(path.read_bytes()).hexdigest() != MODEL_SHA256:
        raise ValueError('PAD model checksum mismatch')
    verify_model_files(path.parent, PAD_DETECTOR_MODELS)
    return path


def _pad_box(image, directory):
    """Use the model's trained RetinaFace crop convention, not the identity SSD box."""
    global _detector, _detector_path
    if _detector is None or _detector_path != str(directory):
        _detector = cv2.dnn.readNetFromCaffe(str(directory / 'pad-retinaface.prototxt'),
                                          str(directory / 'pad-retinaface.caffemodel'))
        _detector_path = str(directory)
    h, w = image.shape[:2]
    frame = image
    if w * h >= 192 * 192:
        ratio = math.sqrt(w / h)
        frame = cv2.resize(image, (int(192 * ratio), int(192 / ratio)))
    _detector.setInput(cv2.dnn.blobFromImage(frame, 1., mean=(104, 117, 123)), 'data')
    detections = np.asarray(_detector.forward('detection_out'))
    if detections.ndim < 2 or detections.shape[-1] != 7 or not np.all(np.isfinite(detections)):
        raise ValueError('Invalid PAD face detection')
    detections = detections.reshape(-1, 7)
    faces = detections[detections[:, 2] >= .6]
    if len(faces) != 1:
        return None
    left, top, right, bottom = faces[0, 3:7] * np.array([w, h, w, h])
    # Upstream bbox is x, y, int(right-left+1), int(bottom-top+1).
    x, y = int(left), int(top)
    right, bottom = x + int(right - left + 1), y + int(bottom - top + 1)
    if not 0 <= x < right < w or not 0 <= y < bottom < h:
        return None
    return dict(zip(('x1', 'y1', 'x2', 'y2'), (x, y, right, bottom)))


def _same_face(first, second):
    """Both detectors must select the same face in this frame; never score another face."""
    intersection = (max(0, min(first['x2'], second['x2']) - max(first['x1'], second['x1'])) *
                    max(0, min(first['y2'], second['y2']) - max(first['y1'], second['y1'])))
    area = lambda box: (box['x2'] - box['x1']) * (box['y2'] - box['y1'])
    union = area(first) + area(second) - intersection
    return union > 0 and intersection / union >= .5


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
    box = _pad_box(image, path.parent)
    if box is None or not _same_face(faces[0]['box'], box):
        return 0.0
    if _network is None or _model_path != str(path):
        _network = cv2.dnn.readNetFromONNX(str(path))
        _model_path = str(path)
    patch = crop_patch(image, box)
    _network.setInput(cv2.dnn.blobFromImage(patch, scalefactor=1.0, swapRB=False, crop=False))
    logits = np.asarray(_network.forward(), dtype=np.float64).reshape(-1)
    if len(logits) != 3 or not np.all(np.isfinite(logits)):
        raise ValueError('Invalid PAD model result')
    probabilities = np.exp(logits - np.max(logits))
    return float(probabilities[1] / np.sum(probabilities))
