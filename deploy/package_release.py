"""Build an allowlisted source delivery bundle without databases or credentials."""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    'README.md', 'API_DOCUMENTATION.md', 'compose.yaml', 'compose.device.yaml', 'compose.tls.yaml', '.dockerignore',
    'BE_smart_lock/smart_lock/config.py', 'BE_smart_lock/smart_lock/run.py',
    'BE_smart_lock/smart_lock/requirements.txt', 'BE_smart_lock/smart_lock/requirements.lock',
    'FE_smart_lock/smartlock/package.json', 'FE_smart_lock/smartlock/package-lock.json',
    'FE_smart_lock/smartlock/index.html', 'FE_smart_lock/smartlock/vite.config.mjs',
    'FE_smart_lock/smartlock/eslint.config.mjs', 'FE_smart_lock/smartlock/README.md',
    'FE_smart_lock/smartlock/tsconfig.json',
    'FE_smart_lock/smartlock/.prettierrc.json',
    'compose.device.tls.yaml', 'paspberry_pi/requirements.pi.txt',
    'packages/smartlock_protocol/pyproject.toml',
)
TREES = {
    'BE_smart_lock/smart_lock/app': {'.py'},
    'BE_smart_lock/smart_lock/tests': {'.py'},
    'FE_smart_lock/smartlock/src': {'.js', '.ts', '.vue', '.css', '.webp'},
    'packages/smartlock_protocol/smartlock_protocol': {'.py'},
    'paspberry_pi/tests': {'.py'},
    'FE_smart_lock/smartlock/tests': {'.cjs'},
    'docs': {'.md'},
    '.github/workflows': {'.yml', '.yaml'},
}


def collect_files():
    files = {ROOT / name for name in FILES}
    for directory, extensions in TREES.items():
        files.update(path for path in (ROOT / directory).rglob('*')
                     if path.is_file() and path.suffix in extensions)
    for directory in ('paspberry_pi', 'paspberry_pi/cv/code', 'paspberry_pi/cv/code/gateway'):
        files.update((ROOT / directory).glob('*.py'))
    files.update(path for path in (ROOT / 'deploy').iterdir()
                 if path.is_file() and path.suffix in {'.py', '.md', '.conf', '.Dockerfile'})
    for path in files:
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(ROOT):
            raise ValueError(f'Invalid release source: {path}')
        if path.suffix == '.py':
            ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
    return sorted(files)


def source_hashes():
    return {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in collect_files() if path.suffix != '.md'}


def package(archive):
    files = collect_files()
    evidence = ROOT / 'releases/verification'
    report = json.loads((evidence / 'verification.json').read_text(encoding='utf-8'))
    if report.get('passed') is not True or report.get('source_hashes') != source_hashes():
        raise ValueError('Run deploy/verify.py after the last source change before packaging')
    manifest = {'created_at': datetime.now(timezone.utc).isoformat(), 'kind': 'software-source-release',
                'excluded': ['secrets', 'databases', 'personal face templates', 'CV models', 'dependencies', 'build outputs'],
                'files': {}}
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in files:
            name = path.relative_to(ROOT).as_posix()
            content = path.read_bytes()
            manifest['files'][name] = hashlib.sha256(content).hexdigest()
            if path.suffix != '.md' and manifest['files'][name] != report['source_hashes'].get(name):
                raise ValueError(f'Source changed during packaging: {name}')
            bundle.writestr(name, content)
        for path in sorted(evidence.iterdir()):
            if path.is_file() and path.suffix in {'.log', '.json'}:
                content = path.read_bytes()
                name = 'verification/' + path.name
                manifest['files'][name] = hashlib.sha256(content).hexdigest()
                bundle.writestr(name, content)
        bundle.writestr('RELEASE_MANIFEST.json', json.dumps(manifest, indent=2))
    # Read back every file and compare bytes to the manifest before delivery.
    with zipfile.ZipFile(archive) as bundle:
        for name, digest in manifest['files'].items():
            if hashlib.sha256(bundle.read(name)).hexdigest() != digest:
                raise ValueError(f'Release checksum mismatch: {name}')
    with archive.open('rb') as handle:
        digest = hashlib.file_digest(handle, 'sha256').hexdigest()
    archive.with_suffix(archive.suffix + '.sha256').write_text(f'{digest}  {archive.name}\n', encoding='ascii')
    print(f'{archive}: {len(files)} files, SHA-256 {digest}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    package(parser.parse_args().archive.resolve())
