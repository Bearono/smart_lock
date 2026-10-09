"""One configurable directory contract for enrollment tools and device inference."""
import os
from pathlib import Path

CV_ROOT = Path(__file__).resolve().parents[1]


def templates_dir():
    return Path(os.environ.get('SMART_LOCK_TEMPLATES_DIR', str(CV_ROOT / 'data/templates/templates')))


def models_dir():
    return Path(os.environ.get('SMART_LOCK_MODELS_DIR', str(CV_ROOT / 'models')))


def embeddings_dir():
    return Path(os.environ.get('SMART_LOCK_EMBEDDINGS_DIR', str(CV_ROOT / 'data/templates/embs')))
