"""Offline backup/restore. Stop all writers first; restore only into an empty directory."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import shutil
import tempfile
import os
from contextlib import closing
import zipfile


def check_database(path):
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as connection:
        if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Database integrity check failed')


def backup(source, archive):
    source, archive = Path(source).resolve(), Path(archive).resolve()
    check_database(source / 'smart_lock.db')
    if archive.is_relative_to(source):
        raise ValueError('Backup archive must be outside the data directory')
    manifest = {}
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as output:
        for path in sorted(source.rglob('*')):
            if path.is_symlink():
                raise ValueError('Symlinks are not supported in data backups')
            if path.is_file():
                name = path.relative_to(source).as_posix()
                with path.open('rb') as handle:
                    manifest[name] = hashlib.file_digest(handle, 'sha256').hexdigest()
                output.write(path, name)
        output.writestr('manifest.json', json.dumps(manifest, sort_keys=True))


def restore(archive, target):
    target = Path(target).resolve()
    target.mkdir(parents=True, exist_ok=True)
    if any(target.iterdir()):
        raise ValueError('Restore requires an empty directory; existing data is never overwritten')
    # Validate the database as well as checksums before exposing restored files.
    with tempfile.TemporaryDirectory(prefix='.smart-lock-restore-', dir=target.parent) as staging:
        stage = Path(staging).resolve()
        if stage.parent != target.parent:
            raise ValueError('Restore staging must remain beside the target')
        _extract_verified(archive, stage)
        check_database(stage / 'smart_lock.db')
        # rmdir refuses if another writer populated the target in the meantime.
        target.rmdir()
        try:
            os.replace(stage, target)
        except OSError:
            target.mkdir(exist_ok=True)
            raise


def _extract_verified(archive, target):
    with zipfile.ZipFile(archive) as source:
        names = source.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate backup entries')
        manifest = json.loads(source.read('manifest.json'))
        if not isinstance(manifest, dict) or 'smart_lock.db' not in manifest:
            raise ValueError('Invalid backup manifest')
        verified = []
        if set(names) != set(manifest) | {'manifest.json'}:
            raise ValueError('Archive contents do not match manifest')
        for name, digest in manifest.items():
            if not isinstance(name, str) or not isinstance(digest, str):
                raise ValueError('Invalid backup entry')
            path = (target / name).resolve()
            if not path.is_relative_to(target) or path == target or '\\' in name:
                raise ValueError('Unsafe backup path')
            with source.open(name) as handle:
                if hashlib.file_digest(handle, 'sha256').hexdigest() != digest:
                    raise ValueError('Backup checksum mismatch')
            verified.append((path, name))
        for path, name in verified:
            path.parent.mkdir(parents=True, exist_ok=True)
            with source.open(name) as handle, path.open('xb') as output:
                shutil.copyfileobj(handle, output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['backup', 'restore'])
    parser.add_argument('archive')
    parser.add_argument('--data', default='/data')
    args = parser.parse_args()
    if args.operation == 'backup':
        backup(args.data, args.archive)
    else:
        restore(args.archive, args.data)
    print('Backup integrity verified. Keep application secrets in a separate protected backup.')
