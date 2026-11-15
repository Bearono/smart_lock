"""Validated, atomic operator-owned templates; never load pickle payloads."""
import os
import tempfile
from pathlib import Path
import numpy as np

try:
    from .paths import templates_dir
except ImportError:
    from paths import templates_dir

DIMENSION = 128


def validate_username(username):
    if (not isinstance(username, str) or not username.strip() or len(username) > 80
            or username != username.strip() or username.endswith('.')
            or username in ('.', '..')
            or any(ord(c) < 32 or c in '/\\:*?"<>|' for c in username)):
        raise ValueError('Use the approved account username without path or control characters')
    return username


def normalize(vector):
    data = np.asarray(vector)
    if data.shape != (DIMENSION,) or not np.issubdtype(data.dtype, np.number):
        raise ValueError('Template must contain exactly 128 numeric values')
    data = data.astype(np.float32)
    if not np.isfinite(data).all():
        raise ValueError('Template contains non-finite values')
    norm = float(np.linalg.norm(data))
    if not np.isfinite(norm) or norm <= 1e-8:
        raise ValueError('Template must have a finite nonzero norm')
    return data / norm


def read_template(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8192:
        raise ValueError('Template must be a small regular NPY file')
    return normalize(np.load(path, allow_pickle=False))


def load_templates(directory=None):
    directory = Path(directory) if directory is not None else templates_dir()
    result = {}
    if not directory.is_dir():
        return result
    for path in sorted(directory.glob('template_*.npy')):
        username = validate_username(path.stem[len('template_'):])
        # Invalid files fail explicitly instead of silently disabling an enrolled account.
        result[username] = read_template(path)
    return result


def install_template(username, vector, directory=None, *, replace=False):
    username = validate_username(username)
    vector = normalize(vector)
    directory = Path(directory) if directory is not None else templates_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f'template_{username}.npy'
    if target.is_symlink():
        raise ValueError('Refusing to replace a symbolic link')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, suffix='.npy', delete=False) as output:
            temporary = Path(output.name)
            np.save(output, vector, allow_pickle=False)
            output.flush()
            os.fsync(output.fileno())
        if replace:
            os.replace(temporary, target)
        else:
            # Linking provides atomic creation without overwriting an existing enrollment.
            os.link(temporary, target)
        return target
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def remove_template(username, directory=None):
    directory = Path(directory) if directory is not None else templates_dir()
    target = directory / f'template_{validate_username(username)}.npy'
    if target.is_symlink():
        raise ValueError('Refusing to remove a symbolic link')
    target.unlink()
