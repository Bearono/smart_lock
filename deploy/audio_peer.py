"""Explicit file/WAV course D2D exchange. No network, playback, recording or lock commands."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'packages/smartlock_protocol'))
from smartlock_protocol.audio_d2d import Peer, canonical


def read_limited(path, limit):
    with Path(path).open('rb') as handle:
        content = handle.read(limit + 1)
    if len(content) > limit:
        raise ValueError('Input exceeds size limit')
    return content


def unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError('Duplicate JSON field')
        result[name] = value
    return result


def read_packet(path, fingerprint_model=None):
    content = read_limited(path, 961024 if Path(path).suffix.lower() == '.wav' else 16384)
    if Path(path).suffix.lower() == '.wav':
        from smartlock_protocol.audio import decode, read_wav
        recording = read_wav(content)
        decoded = decode(recording)
        if fingerprint_model:
            from smartlock_protocol.acoustic_fingerprint import verify
            model = json.loads(read_limited(fingerprint_model, 65536), object_pairs_hook=unique_object)
            outcome = verify(model, content, expected_payload=decoded)
            if not outcome.get('matched'):
                raise ValueError('Acoustic recording does not match the calibrated local model')
        content = decoded
    elif fingerprint_model:
        raise ValueError('A fingerprint model requires a WAV recording')
    return json.loads(content, object_pairs_hook=unique_object)


def write_output(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'wb') as handle:
        handle.write(content)


def packet_bytes(path, packet):
    content = canonical(packet)
    if Path(path).suffix.lower() == '.wav':
        from smartlock_protocol.audio import encode, wav_bytes
        content = wav_bytes(encode(content))
    return content


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('--state', type=Path, default=Path('instance/audio-peer'))
    actions = result.add_subparsers(dest='action', required=True)
    for role in ('issuer', 'receiver'):
        command = actions.add_parser('init-' + role)
        command.add_argument('--identity', required=True)
        command.add_argument('--public-output', type=Path, required=True)
    command = actions.add_parser('request')
    command.add_argument('--sender', required=True)
    command.add_argument('--ttl', type=int, default=300)
    command.add_argument('--output', type=Path, required=True)
    command = actions.add_parser('issue')
    command.add_argument('--input', type=Path, required=True)
    command.add_argument('--receiver-public', type=Path, required=True)
    command.add_argument('--output', type=Path, required=True)
    command = actions.add_parser('accept')
    command.add_argument('--input', type=Path, required=True)
    command.add_argument('--issuer-public', type=Path, required=True)
    command.add_argument('--fingerprint-model', type=Path)
    command.add_argument('--output', type=Path, required=True, help='Confirmation packet output')
    command = actions.add_parser('confirm')
    command.add_argument('--input', type=Path, required=True)
    command.add_argument('--output', type=Path, required=True)
    command = actions.add_parser('seal')
    command.add_argument('--session', required=True)
    command.add_argument('--input', type=Path, required=True, help='Plaintext file, 1..1024 bytes')
    command.add_argument('--output', type=Path, required=True)
    command = actions.add_parser('open')
    command.add_argument('--input', type=Path, required=True)
    command.add_argument('--fingerprint-model', type=Path)
    command.add_argument('--output', type=Path, required=True, help='Decrypted bytes; never executed')
    return result


def main(argv=None):
    arguments = parser()
    args = arguments.parse_args(argv)
    output = args.public_output if args.action.startswith('init-') else args.output
    # Reject existing outputs before any state is consumed. No overwrite switch is provided.
    if output.exists() or output.is_symlink():
        arguments.exit(2, 'Output already exists; choose a new file.\n')
    try:
        if args.action.startswith('init-'):
            peer = Peer(args.state, create=True)
            result = peer.initialize(args.action[len('init-'):], args.identity)
        else:
            peer = Peer(args.state)
            if args.action == 'request':
                result = packet_bytes(output, peer.create_request(args.sender, args.ttl))
            elif args.action == 'issue':
                result = packet_bytes(output, peer.issue(read_packet(args.input), read_limited(args.receiver_public, 4096)))
            elif args.action == 'accept':
                result = packet_bytes(output, peer.accept(read_packet(args.input, args.fingerprint_model),
                                                         read_limited(args.issuer_public, 4096)))
            elif args.action == 'confirm':
                result = packet_bytes(output, peer.verify_confirmation(read_packet(args.input)))
            elif args.action == 'seal':
                result = packet_bytes(output, peer.seal(args.session, read_limited(args.input, 1024)))
            else:
                result = peer.open_message(read_packet(args.input, args.fingerprint_model))
        write_output(output, result)
    except (OSError, ValueError, TypeError) as exc:
        # Never print packet contents, keys, decrypted bytes or credential-bearing tracebacks.
        arguments.exit(2, f'Exchange rejected ({type(exc).__name__}): {exc}\n')
    print(f'{args.action} completed; output={output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
