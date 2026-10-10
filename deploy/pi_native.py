"""Prepare and manage the native CSI profile without modifying system Python."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MARKER = '# Managed by smart-lock native CSI deployment'


def check_runtime():
    """Validate the application dependency closure, excluding unrelated APT tools."""
    from importlib.metadata import distribution
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
    pending = [Requirement(line.strip()) for line in
               (ROOT / 'paspberry_pi/requirements.pi.txt').read_text().splitlines()
               if line.strip() and not line.lstrip().startswith('#')]
    pending.extend(Requirement(name) for name in ('smartlock-protocol', 'picamera2', 'numpy', 'Pillow'))
    visited = set()
    while pending:
        requirement = pending.pop()
        if requirement.marker and not requirement.marker.evaluate({'extra': ''}):
            continue
        installed = distribution(requirement.name)
        if requirement.specifier and not requirement.specifier.contains(installed.version, prereleases=True):
            raise RuntimeError(f'Unsatisfied dependency: {requirement}; installed {installed.version}')
        name = canonicalize_name(requirement.name)
        if name not in visited:
            visited.add(name)
            pending.extend(Requirement(item) for item in installed.requires or ())
    print(f'Application dependency closure verified: {len(visited)} distributions')


def render_unit(root):
    root = Path(root).resolve()
    if not re.fullmatch(r'[A-Za-z0-9_/.-]+', str(root)):
        raise ValueError('Use an absolute installation path without whitespace or unit specifiers')
    return f"""{MARKER}
[Unit]
Description=Smart lock CSI device service
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
WorkingDirectory={root}/paspberry_pi
EnvironmentFile={root}/deploy/.env
Environment=PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
ExecStart={root}/.venv-pi/bin/gunicorn --config {root}/paspberry_pi/gunicorn.conf.py --bind 127.0.0.1:5443 --certfile {root}/deploy/tls/pi-native.crt --keyfile {root}/deploy/tls/pi-native.key --workers 1 --threads 2 --timeout 60 --access-logfile - --error-logfile - app:app
Restart=on-failure
RestartSec=5
TimeoutStopSec=20
MemoryMax=1200M
TasksMax=128
NoNewPrivileges=true
UMask=0077
[Install]
WantedBy=default.target
"""


def prepare():
    if os.geteuid() == 0:
        raise RuntimeError('Run as the device service user, never install pip packages as root')
    subprocess.run([sys.executable, '-c', 'import picamera2, cv2, numpy'], check=True)
    subprocess.run([sys.executable, '-m', 'venv', '--system-site-packages', str(ROOT / '.venv-pi')], check=True)
    python = str(ROOT / '.venv-pi/bin/python')
    env = dict(os.environ, CMAKE_BUILD_PARALLEL_LEVEL='1', DLIB_NO_GUI_SUPPORT='ON', DLIB_USE_CUDA='OFF', OPENBLAS_NUM_THREADS='1')
    subprocess.run([python, '-m', 'pip', '--isolated', 'install', '--index-url', 'https://pypi.org/simple', '--extra-index-url', 'https://pypi.org/simple', 'setuptools==80.9.0', 'wheel==0.45.1', 'packaging==25.0'], check=True, env=env)
    subprocess.run([python, '-m', 'pip', '--isolated', 'install', '--index-url', 'https://pypi.org/simple', '--extra-index-url', 'https://pypi.org/simple', '--no-build-isolation', '-r', str(ROOT / 'paspberry_pi/requirements.pi.txt')], check=True, env=env)
    subprocess.run([python, '-m', 'pip', 'install', '--no-deps', str(ROOT / 'packages/smartlock_protocol')], check=True)
    subprocess.run([python, str(Path(__file__).resolve()), 'check-runtime'], check=True)
    (ROOT / 'instance/pi-native').mkdir(parents=True, exist_ok=True, mode=0o700)
    with (ROOT / 'instance/pi-native/runtime-packages.txt').open('w') as output:
        subprocess.run([python, '-m', 'pip', 'freeze'], stdout=output, check=True)
    print('Native runtime prepared. Model/template and TLS configuration are separate.')


def install_service():
    envfile = ROOT / 'deploy/.env'
    if not envfile.is_file() or envfile.stat().st_mode & 0o077:
        raise ValueError('Provide deploy/.env with mode 0600 before installing the service')
    for path in [ROOT / '.venv-pi/bin/gunicorn', ROOT / 'deploy/tls/pi-native.crt', ROOT / 'deploy/tls/pi-native.key']:
        if not path.is_file():
            raise ValueError(f'Missing native runtime or TLS file: {path.name}')
    destination = Path.home() / '.config/systemd/user/smart-lock-device.service'
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and MARKER not in destination.read_text():
        raise ValueError('Existing unit is not managed by this project; refusing to overwrite it')
    destination.write_text(render_unit(ROOT))
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', '--user', 'enable', '--now', 'smart-lock-device.service'], check=True)
    print('User service enabled. Enable user lingering for boot without an interactive login.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'install-service', 'check-runtime'])
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare()
    elif args.action == 'install-service':
        install_service()
    else:
        check_runtime()
