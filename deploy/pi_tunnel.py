"""Verified SSH forwarding for a workstation backend and a native Pi CSI service.

Keep this process running during laboratory integration. Both listeners use loopback.
This is a development connection, not a permanent production network topology.
"""
import argparse
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--user', required=True)
    parser.add_argument('--identity', type=Path, required=True)
    parser.add_argument('--host-key-alias', default='smartlock.local')
    args = parser.parse_args()
    if any(value.startswith('-') or any(c.isspace() for c in value) for value in (args.host, args.user, args.host_key_alias)):
        parser.error('Invalid SSH host, user or host-key alias')
    if not args.identity.is_file():
        parser.error('SSH identity file not found')
    command = ['ssh', '-NT', '-i', str(args.identity), '-o', 'IdentitiesOnly=yes',
        '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
        '-o', 'ExitOnForwardFailure=yes', '-o', 'ServerAliveInterval=15',
        '-o', 'ServerAliveCountMax=3', '-o', 'HostKeyAlias=' + args.host_key_alias,
        '-L', '127.0.0.1:15443:127.0.0.1:5443',
        '-R', '127.0.0.1:18443:127.0.0.1:8443', args.user + '@' + args.host]
    raise SystemExit(subprocess.call(command))


if __name__ == '__main__':
    main()
