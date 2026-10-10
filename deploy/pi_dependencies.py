"""Install only native CSI prerequisites; run explicitly with sudo on Raspberry Pi OS."""
import argparse
import os
import platform
import pwd
import subprocess


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--linger-user', help='Allow the service user manager to start at boot')
    args = parser.parse_args()
    if os.geteuid() != 0 or platform.machine() not in ('aarch64', 'armv7l'):
        raise SystemExit('Run with sudo on a supported Raspberry Pi OS host')
    if args.linger_user and pwd.getpwnam(args.linger_user).pw_uid == 0:
        raise SystemExit('The device service must not use root')
    env = dict(os.environ, DEBIAN_FRONTEND='noninteractive')
    subprocess.run(['apt-get', 'update'], check=True, env=env)
    subprocess.run(['apt-get', 'install', '-y', '--no-install-recommends',
        'python3-opencv', 'python3-picamera2', 'python3-venv', 'python3-dev',
        'build-essential', 'cmake', 'libopenblas-dev'], check=True, env=env)
    if args.linger_user:
        subprocess.run(['loginctl', 'enable-linger', args.linger_user], check=True)
    print('Native CSI prerequisites installed; system Python packages are managed by apt.')
