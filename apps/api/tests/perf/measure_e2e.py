"""Measure the complete MFA/secure-face/token flow. Only fully successful runs count.

Use --simulate-face with DEVICE_DISPATCH_REQUIRED=false and an offline device URL.
Otherwise a real gateway performs recognition inside open_request.
"""
import argparse
import csv
import os
from pathlib import Path
import statistics
import time

import pyotp
import requests
from client import login_mfa, send_face_result, test_totp_secret

STAGES = ['login', 'open_request', 'face_result', 'confirm', 'token_verify']


def one_run(client, host, username, password, device_id, simulate_face=False):
    stages = {}
    def timed(name, call):
        start = time.perf_counter()
        result = call()
        stages[name] = (time.perf_counter() - start) * 1000
        return result
    def post(path, body, headers=None):
        response = client.post(host + path, json=body, headers=headers or {}, timeout=30)
        response.raise_for_status()
        return response.json()

    token = timed('login', lambda: login_mfa(client, host, username, password))
    headers = {'Authorization': 'Bearer ' + token}
    challenge = timed('open_request', lambda: post('/api/mfa/open-door/request', {'device_id': device_id}, headers))
    if (challenge.get('device_dispatch') or {}).get('status') == 'pending':
        if not simulate_face:
            raise RuntimeError('Device unavailable. Use --simulate-face only for isolated development testing.')
        timed('face_result', lambda: send_face_result(client, host, challenge, username, device_id))
    else:
        # Recognition already happened synchronously; do not send a duplicate result or double-count it.
        stages['face_result'] = 0.0
    body = {'request_id': challenge['request_id']}
    if challenge['requires_totp']:
        body['totp_code'] = pyotp.TOTP(test_totp_secret(username)).now()
    credential = timed('confirm', lambda: post('/api/mfa/open-door/confirm', body, headers))
    result = timed('token_verify', lambda: post('/api/lock/unlock-token/verify', {
        'unlock_token': credential['unlock_token'], 'device_id': credential['device_id']}))
    if result.get('command_accepted') is not True:
        raise RuntimeError('Unlock command was not accepted')
    stages['total'] = sum(stages.values())
    return stages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default=os.getenv('PERF_HOST', 'http://localhost:8000'))
    parser.add_argument('--user', default=os.getenv('PERF_E2E_USER', 'perf_user_001'))
    parser.add_argument('--password', default=os.getenv('PERF_USER_PASSWORD', 'Perf@123456'))
    parser.add_argument('--device', default=os.getenv('PERF_DEVICE_ID', 'door_01'))
    parser.add_argument('--runs', type=int, default=20)
    parser.add_argument('--warmup', type=int, default=2)
    parser.add_argument('--simulate-face', action='store_true')
    args = parser.parse_args()
    if args.runs < 1 or args.warmup < 0:
        parser.error('runs must be positive and warmup nonnegative')
    results, failures = [], 0
    with requests.Session() as client:
        for index in range(args.warmup + args.runs):
            try:
                row = one_run(client, args.host.rstrip('/'), args.user, args.password, args.device, args.simulate_face)
                if index >= args.warmup:
                    results.append(row)
                print(f'run {index + 1}: {row["total"]:.1f} ms')
            except (requests.RequestException, RuntimeError, KeyError) as exc:
                failures += 1
                print(f'run {index + 1}: FAILED: {exc}')
    output = Path(__file__).resolve().parent / 'results'
    output.mkdir(exist_ok=True)
    with (output / 'e2e_stages.csv').open('w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=['run'] + STAGES + ['total'])
        writer.writeheader()
        writer.writerows(dict(row, run=i + 1) for i, row in enumerate(results))
    with (output / 'e2e_summary.csv').open('w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['stage', 'n', 'mean_ms', 'median_ms', 'p95_ms', 'min_ms', 'max_ms', 'stdev_ms'])
        if results:
            for stage in STAGES + ['total']:
                values = sorted(row[stage] for row in results)
                writer.writerow([stage, len(values), statistics.mean(values), statistics.median(values),
                                 values[round(.95 * (len(values) - 1))], min(values), max(values),
                                 statistics.stdev(values) if len(values) > 1 else 0])
    print(f'Successful measured runs: {len(results)}; failed runs (including warmup): {failures}')
    return 1 if failures or not results else 0


if __name__ == '__main__':
    raise SystemExit(main())
