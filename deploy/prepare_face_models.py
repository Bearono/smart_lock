"""Install pinned identity/PAD detector models; device requests never download models."""
import argparse
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps/device/cv/code'))
from model_manifest import MODELS, PAD_DETECTOR_MODELS, verify_model_files

ALL_MODELS = {**MODELS, **PAD_DETECTOR_MODELS}


def prepare(directory):
    directory.mkdir(parents=True, exist_ok=True)
    for name, (url, digest) in ALL_MODELS.items():
        target = directory / name
        if target.exists() or target.is_symlink():
            with target.open('rb') as source:
                if target.is_symlink() or hashlib.file_digest(source, 'sha256').hexdigest() != digest:
                    raise ValueError(f'Refusing to overwrite unexpected model: {name}')
            continue
        temporary = None
        try:
            with urllib.request.urlopen(url, timeout=45) as response, tempfile.NamedTemporaryFile(
                dir=directory, delete=False) as output:
                temporary = Path(output.name)
                size = 0
                while chunk := response.read(65536):
                    size += len(chunk)
                    if size > 20 * 1024 * 1024:
                        raise ValueError('Model exceeds download size limit')
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            with temporary.open('rb') as source:
                if hashlib.file_digest(source, 'sha256').hexdigest() != digest:
                    raise ValueError(f'Download checksum mismatch: {name}')
            os.link(temporary, target)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
    verify_model_files(directory, ALL_MODELS)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=Path(__file__).resolve().parent / 'device/models')
    parser.add_argument('--download', action='store_true', help='Explicitly download missing pinned files')
    args = parser.parse_args()
    try:
        if args.download:
            prepare(args.directory)
        else:
            verify_model_files(args.directory, ALL_MODELS)
        print('Pinned identity and PAD detector models verified.')
    except (ValueError, OSError) as exc:
        parser.exit(1, f'Model preparation failed: {exc}\n')
