"""Use dlib's maintained API without the retired pkg_resources import chain."""
from functools import lru_cache
from hashlib import sha256
from importlib.metadata import distribution
from pathlib import Path

MODEL_HASHES = {
    'shape_predictor_5_face_landmarks.dat': 'c4b1e9804792707d3a405c2c16a80a20269e6675021f64a41d30fffafbc41888',
    'dlib_face_recognition_resnet_model_v1.dat': '55533b28a95800a551ba546ba62fe69625c7e95a7061c338adffead08719da30',
}


def model_path(filename):
    package = distribution('face-recognition-models')
    path = Path(package.locate_file('face_recognition_models/models/' + filename))
    if path.is_symlink() or not path.is_file():
        raise ValueError('Missing dlib embedding model')
    with path.open('rb') as stream:
        digest = sha256(stream.read()).hexdigest()
    if digest != MODEL_HASHES[filename]:
        raise ValueError('Dlib embedding model integrity check failed')
    return str(path)


@lru_cache(maxsize=1)
def load_models():
    import dlib
    return (dlib.shape_predictor(model_path('shape_predictor_5_face_landmarks.dat')),
            dlib.face_recognition_model_v1(model_path('dlib_face_recognition_resnet_model_v1.dat')))


def encode_face(image_rgb, location):
    import dlib
    predictor, encoder = load_models()
    top, right, bottom, left = location
    landmarks = predictor(image_rgb, dlib.rectangle(left, top, right, bottom))
    # Matches the historical face_encodings default: small landmarks and one jitter.
    return encoder.compute_face_descriptor(image_rgb, landmarks, 1)
