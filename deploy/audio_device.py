"""Explicit bounded audio I/O and calibrated acoustic-path experiments."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

import numpy as np

from smartlock_protocol import acoustic_fingerprint as fingerprint
from smartlock_protocol.audio import RATE, decode, encode, read_wav, wav_bytes


def read_bounded(path, limit=RATE * 20 + 1024):
    with Path(path).open('rb') as stream:
        value = stream.read(limit + 1)
    if len(value) > limit:
        raise ValueError('Input exceeds size limit')
    return value


def save_new(path, content):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(content)


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def load_json(path):
    return json.loads(read_bounded(path, 256 * 1024).decode('utf-8'))


def sound_backend():
    try:
        import sounddevice
    except (ImportError, OSError) as error:
        raise RuntimeError('Install smartlock-protocol[audio-device] and the system PortAudio library') from error
    return sounddevice


@contextmanager
def _audio_thread():
    """WASAPI requires COM on the calling thread, including GUI worker threads."""
    if sys.platform != 'win32':
        yield
        return
    import ctypes
    ole = ctypes.WinDLL('ole32')
    ole.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    ole.CoInitializeEx.restype = ctypes.c_int32
    ole.CoUninitialize.argtypes = []
    ole.CoUninitialize.restype = None
    result = ole.CoInitializeEx(None, 0) & 0xffffffff  # COINIT_MULTITHREADED
    # An existing STA belongs to its caller; leave its apartment and reference count alone.
    if result not in (0, 1, 0x80010106):  # S_OK, S_FALSE, RPC_E_CHANGED_MODE
        raise RuntimeError(f'Audio thread COM initialization failed: 0x{result:08x}')
    try:
        yield
    finally:
        if result in (0, 1):
            ole.CoUninitialize()


@_audio_thread()
def list_devices(backend=None):
    sd = backend if backend is not None else sound_backend()
    return [dict(dict(value), index=i, host_api=sd.query_hostapis(value['hostapi'])['name'])
            for i, value in enumerate(sd.query_devices())]


def _input_options(sd, device, wasapi_raw):
    if not wasapi_raw:
        return {}
    if sys.platform != 'win32' or sd.query_hostapis(sd.query_devices(device)['hostapi'])['name'] != 'Windows WASAPI':
        raise ValueError('Raw input requires an explicitly selected Windows WASAPI microphone')
    settings = sd.WasapiSettings()
    # sounddevice 0.5.6 exposes PortAudio's documented WASAPI extension via this struct.
    if not hasattr(settings, '_streaminfo') or not hasattr(settings._streaminfo, 'streamOption') or not hasattr(sd._lib, 'eStreamOptionRaw'):
        raise RuntimeError('Installed audio backend does not expose WASAPI raw input')
    settings._streaminfo.streamOption = sd._lib.eStreamOptionRaw
    return {'extra_settings': settings}


@_audio_thread()
def record(seconds, device, backend=None, *, wasapi_raw=False):
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0.1 <= seconds <= 10:
        raise ValueError('Recording duration must be between 0.1 and 10 seconds')
    if device is None:
        raise ValueError('Select an explicit input device')
    if type(wasapi_raw) is not bool:
        raise ValueError('Raw input option must be a boolean')
    sd = backend if backend is not None else sound_backend()
    options = _input_options(sd, device, wasapi_raw)
    frames = int(seconds * RATE)
    sd.check_input_settings(device=device, channels=1, dtype='int16', samplerate=RATE, **options)
    blocks = []
    # PortAudio callback + bounded wait: a stalled device cannot hang indefinitely.
    remaining = frames
    failure = []
    import threading
    done = threading.Event()

    def callback(data, count, timing, status):
        nonlocal remaining
        if status:
            failure.append(str(status))
            done.set()
            raise sd.CallbackAbort
        take = min(remaining, count)
        blocks.append(np.array(data[:take, 0], copy=True))
        remaining -= take
        if remaining <= 0:
            done.set()
            raise sd.CallbackStop

    stream = sd.InputStream(device=device, channels=1, dtype='int16', samplerate=RATE,
                            callback=callback, blocksize=1024, **options)
    try:
        stream.start()
        if not done.wait(seconds + 3):
            raise RuntimeError('Audio device stopped delivering samples')
    finally:
        try:
            stream.abort()
        finally:
            stream.close()
    if failure or remaining or not blocks:
        raise RuntimeError('Incomplete audio capture: ' + '; '.join(failure))
    samples = np.concatenate(blocks).astype(float) / 32767
    samples = np.clip(samples, -1, 1)
    return wav_bytes(samples)


@_audio_thread()
def play(recording, device, gain=0.2, backend=None):
    if device is None:
        raise ValueError('Select an explicit output device')
    if type(gain) not in (int, float) or not math.isfinite(gain) or not 0 < gain <= 0.5:
        raise ValueError('Playback gain must be in (0, 0.5]')
    samples = read_wav(recording) * gain
    if not len(samples):
        raise ValueError('Empty recording')
    sd = backend if backend is not None else sound_backend()
    sd.check_output_settings(device=device, channels=1, dtype='float32', samplerate=RATE)
    import threading
    done = threading.Event()
    position = 0
    failure = []

    def callback(output, count, timing, status):
        nonlocal position
        if status:
            failure.append(str(status))
            done.set()
            raise sd.CallbackAbort
        take = min(count, len(samples) - position)
        output[:] = 0
        output[:take, 0] = samples[position:position + take]
        position += take
        if position == len(samples):
            raise sd.CallbackStop

    stream = sd.OutputStream(device=device, channels=1, dtype='float32', samplerate=RATE,
                             callback=callback, finished_callback=done.set, blocksize=1024)
    try:
        stream.start()
        if not done.wait(len(samples) / RATE + 3):
            raise RuntimeError('Audio output did not finish within the deadline')
    finally:
        try:
            stream.abort()
        finally:
            stream.close()
    if failure or position != len(samples):
        raise RuntimeError('Audio playback failed: ' + '; '.join(failure))


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest='command', required=True)
    commands.add_parser('devices')
    encode_cmd = commands.add_parser('encode')
    encode_cmd.add_argument('--input', required=True, type=Path)
    encode_cmd.add_argument('--output', required=True, type=Path)
    decode_cmd = commands.add_parser('decode')
    decode_cmd.add_argument('--input', required=True, type=Path)
    decode_cmd.add_argument('--output', required=True, type=Path)
    probe = commands.add_parser('probe')
    probe.add_argument('--output', required=True, type=Path)
    rec = commands.add_parser('record')
    rec.add_argument('--device', required=True, type=int)
    rec.add_argument('--seconds', default=5.0, type=float)
    rec.add_argument('--output', required=True, type=Path)
    rec.add_argument('--wasapi-raw', action='store_true', help='Request unprocessed input from a Windows WASAPI microphone')
    playback = commands.add_parser('play')
    playback.add_argument('--device', required=True, type=int)
    playback.add_argument('--input', required=True, type=Path)
    playback.add_argument('--gain', default=0.2, type=float)
    enroll = commands.add_parser('enroll')
    enroll.add_argument('--device-id', required=True)
    enroll.add_argument('--recordings', nargs='+', type=Path, required=True)
    enroll.add_argument('--output', required=True, type=Path)
    for name in ('calibrate', 'evaluate'):
        sub = commands.add_parser(name)
        sub.add_argument('--model', required=True, type=Path)
        sub.add_argument('--genuine', nargs='+', type=Path, required=True)
        sub.add_argument('--impostor', nargs='+', type=Path, required=True)
        sub.add_argument('--output', required=True, type=Path)
    verify = commands.add_parser('verify')
    verify.add_argument('--model', required=True, type=Path)
    verify.add_argument('--input', required=True, type=Path)
    verify.add_argument('--expected-payload', type=Path)
    verify.add_argument('--output', required=True, type=Path)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    if getattr(args, 'output', None) is not None and args.output.exists():
        raise FileExistsError('Output already exists; choose a new trial filename')
    if args.command == 'devices':
        print(json.dumps(list_devices(), ensure_ascii=False, indent=2))
        return 0
    if args.command == 'play':
        play(read_bounded(args.input), args.device, args.gain)
        return 0
    if args.command == 'record':
        output = record(args.seconds, args.device, wasapi_raw=args.wasapi_raw)
    elif args.command == 'encode':
        output = wav_bytes(encode(read_bounded(args.input, 2048)))
    elif args.command == 'decode':
        output = decode(read_wav(read_bounded(args.input)))
    elif args.command == 'probe':
        challenge = json.dumps({'version': 'SL-acoustic-probe-1', 'nonce': os.urandom(16).hex(),
                                'created_at': int(time.time())}, sort_keys=True, separators=(',', ':')).encode()
        output = wav_bytes(encode(challenge))
    elif args.command == 'enroll':
        output = json_bytes(fingerprint.enroll(args.device_id, [read_bounded(path) for path in args.recordings]))
    elif args.command in ('calibrate', 'evaluate'):
        method = getattr(fingerprint, args.command)
        result = method(load_json(args.model), [read_bounded(path) for path in args.genuine],
                        [read_bounded(path) for path in args.impostor])
        output = json_bytes(result)
    else:
        expected = read_bounded(args.expected_payload, 2048) if args.expected_payload else None
        result = fingerprint.verify(load_json(args.model), read_bounded(args.input), expected)
        output = json_bytes(result)
        save_new(args.output, output)
        print(json.dumps({'matched': result['matched'], 'cryptographic_identity_verified': False}))
        return 0 if result['matched'] else 1
    save_new(args.output, output)
    print(json.dumps({'output': str(args.output), 'bytes': len(output),
                      'sha256': hashlib.sha256(output).hexdigest()}))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
