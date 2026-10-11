"""Explicit bounded workstation/Pi soak test; no startup or reconnect installation."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
PROBE = '''
import json, requests
from run import app
from app.models import Device, DeviceProvisioning
with app.app_context():
    d=Device.query.filter_by(device_id="pi_csi_01").one().to_dict()
    origin=DeviceProvisioning.query.filter_by(device_id="pi_csi_01").one().service_url
    r=requests.get(origin+"/health/ready", timeout=10)
    print(json.dumps({"ready":r.status_code,"online":d["is_online"],"camera":d["camera_status"],
                      "actuator":d["actuator_status"],"lock":d["reported_status"]}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=1800)
    parser.add_argument('--interval', type=int, default=60)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 60 <= args.seconds <= 7200 or not 5 <= args.interval <= 60:
        parser.error('duration 60..7200 seconds; interval 5..60 seconds')
    if args.output.exists():
        parser.error('output exists; choose a new test file')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {'started_at': datetime.now(timezone.utc).isoformat(),
              'scope': 'bounded current workstation/Pi uptime; excludes power-cut and lock actuation',
              'completed': False, 'passed': False, 'samples': []}
    started = time.monotonic()
    while True:
        row = {'elapsed_seconds': round(time.monotonic() - started, 1)}
        try:
            result = subprocess.run(['docker', 'compose', '-f', 'compose.yaml', '-f', 'compose.tls.yaml',
                                     'exec', '-T', 'backend', 'python', '-c', PROBE],
                                    cwd=ROOT, capture_output=True, text=True, timeout=25, check=True)
            row.update(json.loads(result.stdout))
            row['passed'] = row['ready'] == 200 and row['online'] and row['camera'] == 'ONLINE'
        except (subprocess.SubprocessError, ValueError, OSError):
            row['passed'] = False
            row['error'] = 'probe_failed'  # Do not store raw logs or credential-bearing tracebacks.
        report['samples'].append(row)
        elapsed = time.monotonic() - started
        report['elapsed_seconds'] = round(elapsed, 1)
        if elapsed >= args.seconds:
            report['completed'] = True
            report['passed'] = all(sample['passed'] for sample in report['samples'])
        args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(f"Sample {len(report['samples'])}: passed={row['passed']}; elapsed={elapsed:.0f}s", flush=True)
        if report['completed']:
            return 0 if report['passed'] else 1
        time.sleep(min(args.interval, args.seconds - elapsed))


if __name__ == '__main__':
    raise SystemExit(main())
