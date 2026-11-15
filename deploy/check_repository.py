"""Offline workspace, source-boundary and current-document checks."""
import ast
import os
from pathlib import Path
import re
import subprocess
import tomllib
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
IGNORED = {'.git', '.local', '.tools', '.gradle', '__pycache__', 'node_modules',
           'build', 'dist', 'outputs', 'releases', 'instance', 'test-artifacts'}
FORBIDDEN_SUFFIXES = {'.pem', '.key', '.keystore', '.jks', '.p12', '.pfx', '.db',
                      '.sqlite', '.sqlite3', '.pyc', '.class', '.apk', '.whl', '.npy', '.caffemodel'}


def source_files(root):
    """Use this repository's index, or a safe file walk in an extracted release."""
    try:
        git_root = subprocess.run(['git', '-C', str(root), 'rev-parse', '--show-toplevel'],
                                  capture_output=True, text=True, check=False)
        if git_root.returncode == 0 and Path(git_root.stdout.strip()).resolve() == root.resolve():
            tracked = subprocess.check_output(
                ['git', '-C', str(root), 'ls-files', '--cached', '--others', '--exclude-standard', '-z'])
            return sorted({root / name for name in tracked.decode('utf-8').split('\0')
                           if name and (root / name).is_file()})
    except FileNotFoundError:
        pass
    paths = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [name for name in dirs if name not in IGNORED
                   and not name.startswith('.venv') and not name.endswith('.egg-info')]
        paths.extend(Path(directory) / name for name in files)
    return sorted(paths)


def check_documents(root, documents):
    errors = []
    for document in documents:
        if not document.is_file():
            errors.append('Missing current document: ' + str(document.relative_to(root)))
            continue
        content = document.read_text(encoding='utf-8-sig')
        for target in re.findall(r'\[[^\]]*\]\(([^\s)]+)\)', content):
            if target.startswith('#') or urlsplit(target).scheme:
                continue
            path = (document.parent / unquote(target.split('#')[0])).resolve()
            if not path.is_relative_to(root.resolve()) or not path.exists():
                errors.append(f'Broken or external local link in {document.relative_to(root)}: {target}')
    return errors


def check_imports(root, paths):
    errors = []
    for path in paths:
        name = path.relative_to(root).as_posix()
        if path.suffix != '.py' or not name.startswith(('apps/api/app/', 'apps/device/', 'apps/lock_sim/', 'packages/')):
            continue
        if '/tests/' in name:
            continue
        tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
        for node in ast.walk(tree):
            imports = ([node.module] if isinstance(node, ast.ImportFrom)
                       else [item.name for item in node.names] if isinstance(node, ast.Import) else [])
            for imported in filter(None, imports):
                parts = imported.split('.')
                if parts[-1] in ('AesCBCalgorithm', 'ECCalgorithm', 'gen_keys') or parts[0] in ('examples', 'tests'):
                    errors.append('Runtime imports an experiment/test: ' + name)
                if name.startswith('packages/') and parts[0] in ('flask', 'flask_sqlalchemy', 'flask_jwt_extended', 'app', 'apps'):
                    errors.append('Shared protocol imports an application/framework: ' + name)
                if (name.startswith('apps/api/app/') and '/routes/' not in name
                        and name != 'apps/api/app/__init__.py' and imported.startswith('app.routes')):
                    errors.append('Business service depends on an HTTP route: ' + name)
    return errors


def audit(root=ROOT):
    root = Path(root).resolve()
    paths = source_files(root)
    errors = []
    workspace = tomllib.loads((root / 'workspace.toml').read_text(encoding='utf-8'))
    documents = [root / name for name in ('README.md', 'CONTRIBUTING.md', 'SECURITY.md', 'deploy/README.md')]
    for section in ('applications', 'libraries'):
        for name, component in workspace[section].items():
            directory = (root / component['path']).resolve()
            if not directory.is_relative_to(root) or not directory.is_dir():
                errors.append('Missing or external workspace component: ' + name)
                continue
            documents.append(directory / 'README.md')
            for key in ('entrypoint', 'dependencies'):
                if key in component:
                    target = (directory / component[key]).resolve()
                    if not target.is_relative_to(directory) or not target.is_file():
                        errors.append('Missing or external component ' + key + ': ' + name)
    for old in ('BE_smart_lock', 'FE_smart_lock', 'paspberry_pi', 'android', 'wanganCV'):
        if (root / old).exists():
            errors.append('Retired root directory reintroduced: ' + old)
    for directory in ('apps/api/spake2', 'apps/device/spake2', 'apps/device/cv/code/gateway/spake2'):
        if (root / directory).exists():
            errors.append('Vendored dependency shadows the pinned installation: ' + directory)
    local = workspace['boundaries']['local_only']
    for path in paths:
        name = path.relative_to(root).as_posix()
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            errors.append('Source is a symlink or outside the workspace: ' + name)
        if (set(path.relative_to(root).parts) & {'venv', '__pycache__', 'node_modules', '.tools', '.gradle', 'build', 'instance'}
                or any(name == item or name.startswith(item + '/') for item in local)
                or '/static/captures/' in name or '/data/templates/' in name
                or name.startswith('apps/api/tests/perf/results/')
                or path.suffix.lower() in FORBIDDEN_SUFFIXES
                or path.name == '.env'):
            errors.append('Generated or sensitive artifact is tracked: ' + name)
        if name.startswith('docs/') and '/archive/' not in name and path.suffix == '.md':
            documents.append(path)
        if name.startswith('examples/') and path.name == 'README.md':
            documents.append(path)
    android = root / 'apps/android/app/src/main'
    for path in android.rglob('*.java'):
        if re.search(r'\b(OfdmCodec|RobustOfdmCodec|D2dCrypto|PcmRecorder|WaveFile|RecordingBudget)\b',
                     path.read_text(encoding='utf-8')):
            errors.append('Android runtime contains audio laboratory code: ' + str(path.relative_to(root)))
    errors.extend(check_documents(root, sorted(set(documents))))
    errors.extend(check_imports(root, paths))
    return errors, len(set(documents))


def check():
    errors, count = audit()
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'Repository checks passed: {count} current documents; workspace, import and artifact boundaries.')


if __name__ == '__main__':
    check()
