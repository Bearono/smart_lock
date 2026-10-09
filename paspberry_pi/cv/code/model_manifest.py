"""Pinned OpenCV face detector assets, verified before loading in production."""
import hashlib
from pathlib import Path

MODELS = {
    'deploy.prototxt': (
        'https://raw.githubusercontent.com/opencv/opencv/4.11.0/samples/dnn/face_detector/deploy.prototxt',
        'dcd661dc48fc9de0a341db1f666a2164ea63a67265c7f779bc12d6b3f2fa67e9'),
    'res10_300x300_ssd_iter_140000.caffemodel': (
        'https://raw.githubusercontent.com/opencv/opencv_3rdparty/dnn_samples_face_detector_20170830/res10_300x300_ssd_iter_140000.caffemodel',
        '2a56a11a57a4a295956b0660b4a3d76bbdca2206c4961cea8efe7d95c7cb2f2d'),
}


def verify_models(directory):
    directory = Path(directory)
    for name, (_, digest) in MODELS.items():
        path = directory / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
            raise ValueError(f'Missing or invalid face model: {name}')
        with path.open('rb') as source:
            actual = hashlib.file_digest(source, 'sha256').hexdigest()
        if actual != digest:
            raise ValueError(f'Face model checksum mismatch: {name}')
