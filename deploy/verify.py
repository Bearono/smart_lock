"""Run repeatable software release checks; stop on failure and save evidence."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from package_release import source_hashes

ROOT = Path(__file__).resolve().parents[1]


def verify(output):
    npm = shutil.which('npm.cmd' if sys.platform == 'win32' else 'npm')
    if npm is None:
        raise RuntimeError('Node/npm is required for software acceptance')
    frontend = ROOT / 'FE_smart_lock/smartlock'
    checks = [
        ('backend', [sys.executable, '-B', '-m', 'unittest', 'discover', '-s',
                     'BE_smart_lock/smart_lock/tests', '-p', 'test_*.py', '-v'], ROOT),
        ('frontend-tests', [npm, 'test'], frontend),
        ('frontend-lint', [npm, 'run', 'lint'], frontend),
        ('frontend-build', [npm, 'run', 'build'], frontend),
    ]
    output.mkdir(parents=True, exist_ok=True)
    report = {'created_at': datetime.now(timezone.utc).isoformat(),
              'scope': 'software automated acceptance; excludes browser, container runtime and hardware',
              'passed': False, 'checks': [], 'source_hashes': source_hashes()}
    for name, command, directory in checks:
        start = time.monotonic()
        print(f'Running {name}', flush=True)
        try:
            result = subprocess.run(command, cwd=directory, capture_output=True, timeout=600)
            log = result.stdout + result.stderr
            code = result.returncode
        except subprocess.TimeoutExpired as exc:
            log = (exc.stdout or b'') + (exc.stderr or b'') + b'\nVerification timed out\n'
            code = 124
        (output / f'{name}.log').write_bytes(log)
        report['checks'].append({'name': name, 'exit_code': code,
                                 'seconds': round(time.monotonic() - start, 3)})
        (output / 'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        if code:
            print(log.decode('utf-8', errors='replace'), file=sys.stderr)
            return code
    if report['source_hashes'] != source_hashes():
        print('Source changed during verification; rerun against a stable workspace', file=sys.stderr)
        return 1
    report['passed'] = True
    (output / 'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(f'All automated software checks passed. Evidence: {output}')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'releases/verification')
    args = parser.parse_args()
    raise SystemExit(verify(args.output.resolve()))
