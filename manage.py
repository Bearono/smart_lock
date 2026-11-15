"""Cross-platform workspace entry point; use the project's Python environment."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['check', 'verify', 'web-dev', 'web-build',
                                          'web-test', 'android-build', 'android-test', 'package'])
    args, extra = parser.parse_known_args()
    scripts = {'check': 'deploy/check_repository.py', 'verify': 'deploy/verify.py',
               'android-build': 'apps/android/build_sdk.py', 'android-test': 'apps/android/test_jvm.py',
               'package': 'deploy/package_release.py'}
    if args.command in scripts:
        command = [sys.executable, str(ROOT / scripts[args.command]), *extra]
    else:
        npm = shutil.which('npm.cmd' if sys.platform == 'win32' else 'npm')
        if not npm:
            parser.error('Install the Node version declared by apps/web/package.json')
        action = {'web-dev': 'serve', 'web-build': 'build', 'web-test': 'test'}[args.command]
        command = [npm, '--prefix', str(ROOT / 'apps/web'), 'run', action]
        if extra:
            command += ['--', *extra]
    return subprocess.call(command, cwd=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
