"""Offline source-boundary and current-document link checks (not a secret scanner)."""
import ast
from pathlib import Path
import re
import subprocess
import tomllib
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def check():
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    errors = []
    workspace = tomllib.loads((ROOT / 'workspace.toml').read_text(encoding='utf-8'))
    for section in ('applications', 'libraries'):
        for name, component in workspace[section].items():
            directory = (ROOT / component['path']).resolve()
            if not directory.is_relative_to(ROOT) or not directory.is_dir():
                errors.append('Missing or external workspace component: ' + name)
                continue
            for key in ('entrypoint', 'dependencies'):
                if key in component and not (directory / component[key]).is_file():
                    errors.append('Missing component ' + key + ': ' + name)
    for old in ('BE_smart_lock', 'FE_smart_lock', 'paspberry_pi', 'android', 'wanganCV'):
        if (ROOT / old).exists():
            errors.append('Retired root directory reintroduced: ' + old)
    for directory in ('apps/api/spake2', 'apps/device/spake2', 'apps/device/cv/code/gateway/spake2'):
        if (ROOT / directory).exists():
            errors.append('Vendored dependency shadows the pinned installation: ' + directory)
    for name in filter(None, tracked):
        if ('/venv/' in name or '/__pycache__/' in name or '/static/captures/' in name
                or '/data/templates/' in name or '/instance/' in name
                or name.endswith(('.pem', '.db', '.npy', '.caffemodel'))):
            errors.append('Generated or sensitive artifact is tracked: ' + name)
    documents = [ROOT / 'README.md', ROOT / 'API_DOCUMENTATION.md', ROOT / 'deploy/README.md',
                 ROOT / 'apps/web/README.md', *sorted((ROOT / 'docs').glob('*.md'))]
    for document in documents:
        if not document.is_file():
            errors.append('Missing current document: ' + str(document.relative_to(ROOT)))
            continue
        for target in re.findall(r'\[[^\]]*\]\(([^\s)]+)\)', document.read_text(encoding='utf-8')):
            if target.startswith('#') or urlsplit(target).scheme:
                continue
            path = (document.parent / unquote(target.split('#')[0])).resolve()
            if not path.exists():
                errors.append(f'Broken link in {document.relative_to(ROOT)}: {target}')
    for directory in ('apps/api/app', 'apps/device'):
        for path in (ROOT / directory).rglob('*.py'):
            if any(part in ('venv', '__pycache__') for part in path.relative_to(ROOT).parts):
                continue
            tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
            for node in ast.walk(tree):
                names = ([node.module] if isinstance(node, ast.ImportFrom)
                         else [item.name for item in node.names] if isinstance(node, ast.Import) else [])
                if any(name and name.split('.')[-1] in ('AesCBCalgorithm', 'ECCalgorithm', 'gen_keys') for name in names):
                    errors.append('Retired crypto imported by runtime: ' + str(path.relative_to(ROOT)))
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'Repository checks passed: {len(documents)} current documents; source artifact and legacy crypto boundaries.')


if __name__ == '__main__':
    check()
