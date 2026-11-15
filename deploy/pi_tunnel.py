"""Verified SSH forwarding for a workstation backend and a native Pi CSI service.

Keep this process running during laboratory integration. Both listeners use loopback.
This is a development connection, not a permanent production network topology.
"""
import argparse
import ipaddress
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--user', required=True)
    parser.add_argument('--identity', type=Path, required=True)
    parser.add_argument('--host-key-alias', default='smartlock.local')
    parser.add_argument('--bind-address', help='Local LAN IP to use when a VPN/proxy selects the wrong route')
    args = parser.parse_args()
    if any(value.startswith('-') or any(c.isspace() for c in value) for value in (args.host, args.user, args.host_key_alias)):
        parser.error('Invalid SSH host, user or host-key alias')
    if not args.identity.is_file():
        parser.error('SSH identity file not found')
    if args.bind_address:
        try:
            address = ipaddress.ip_address(args.bind_address)
            if address.is_unspecified or address.is_multicast:
                raise ValueError('Expected a local unicast address')
        except ValueError:
            parser.error('--bind-address must be a local unicast IP address')
    command = ['ssh', '-NT', '-i', str(args.identity), '-o', 'IdentitiesOnly=yes',
        '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
        '-o', 'ExitOnForwardFailure=yes', '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=15',
        '-o', 'ServerAliveCountMax=3', '-o', 'HostKeyAlias=' + args.host_key_alias,
        '-L', '127.0.0.1:15443:127.0.0.1:5443',
        '-R', '127.0.0.1:18443:127.0.0.1:8443']
    if args.bind_address:
        command.extend(['-b', str(address)])
    command.append(args.user + '@' + args.host)
    raise SystemExit(subprocess.call(command))


if __name__ == '__main__':
    main()
