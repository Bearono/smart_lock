"""Pinned face detector assets, verified before loading in production."""

import hashlib
from pathlib import Path

MODELS = {
    "deploy.prototxt": (
        "https://raw.githubusercontent.com/opencv/opencv/4.11.0/samples/dnn/face_detector/deploy.prototxt",
        "dcd661dc48fc9de0a341db1f666a2164ea63a67265c7f779bc12d6b3f2fa67e9",
    ),
    "res10_300x300_ssd_iter_140000.caffemodel": (
        "https://raw.githubusercontent.com/opencv/opencv_3rdparty/dnn_samples_face_detector_20170830/res10_300x300_ssd_iter_140000.caffemodel",
        "2a56a11a57a4a295956b0660b4a3d76bbdca2206c4961cea8efe7d95c7cb2f2d",
    ),
}

PAD_DETECTOR_MODELS = {
    "pad-retinaface.prototxt": (
        "https://raw.githubusercontent.com/minivision-ai/Silent-Face-Anti-Spoofing/b6d5f04ad78778917853b25c778acef6d5626d15/resources/detection_model/deploy.prototxt",
        "9fe2f141b4baee039ed9442da2833e216af40a6ff3e639e7b39258812bcda808",
    ),
    "pad-retinaface.caffemodel": (
        "https://raw.githubusercontent.com/minivision-ai/Silent-Face-Anti-Spoofing/b6d5f04ad78778917853b25c778acef6d5626d15/resources/detection_model/Widerface-RetinaFace.caffemodel",
        "d08338a2c207df16a9c566f767fea67fb43ba6fff76ce11e938fe3fabefb9402",
    ),
}


def verify_models(directory):
    verify_model_files(directory, MODELS)


def verify_model_files(directory, manifest):
    directory = Path(directory)
    for name, (_, digest) in manifest.items():
        path = directory / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
            raise ValueError(f"Missing or invalid face model: {name}")
        with path.open("rb") as source:
            actual = hashlib.file_digest(source, "sha256").hexdigest()
        if actual != digest:
            raise ValueError(f"Face model checksum mismatch: {name}")
