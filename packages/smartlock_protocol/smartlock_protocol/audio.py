"""Bounded mono OFDM/WAV transport. CRC detects damage, not attackers.

Carry an authenticated v3 envelope, never a naked key or trusted identity.
No sound device is opened and no physical fingerprint claim is made here.
"""
import io
import struct
import wave
import zlib
import json
import numpy as np

RATE, FFT, PREFIX = 48000, 256, 64
BINS = np.arange(16, 80)
MAX_PAYLOAD = 2048
SYMBOL = FFT + PREFIX
TRAINING = np.random.default_rng(3101).choice((-1.0, 1.0), (2, len(BINS)))


def envelope_wav(packet):
    """Serialize a v3 ciphertext envelope. Receiver must still authenticate and claim replay receipt."""
    from .v3 import VERSION
    from .v2 import canonical_json
    if (not isinstance(packet, dict) or not isinstance(packet.get('header'), dict)
            or packet['header'].get('version') != VERSION):
        raise ValueError('Only v3 encrypted envelopes may use this adapter')
    return wav_bytes(encode(canonical_json(packet)))


def envelope_from_wav(recording):
    """Recover an UNTRUSTED envelope for the normal backend verifier, never plaintext or authority."""
    from .v3 import VERSION
    packet = json.loads(decode(read_wav(recording)).decode('utf-8'))
    if (not isinstance(packet, dict) or not isinstance(packet.get('header'), dict)
            or packet['header'].get('version') != VERSION or not isinstance(packet.get('ciphertext'), str)):
        raise ValueError('Invalid encrypted envelope')
    return packet


def symbol(carriers):
    spectrum = np.zeros(FFT, dtype=complex)
    spectrum[BINS] = carriers
    spectrum[-BINS] = np.conjugate(carriers)
    samples = np.fft.ifft(spectrum).real
    return np.concatenate((samples[-PREFIX:], samples))


PREAMBLE = np.concatenate([symbol(row) for row in TRAINING])


def encode(payload):
    if not isinstance(payload, bytes) or not 1 <= len(payload) <= MAX_PAYLOAD:
        raise ValueError('OFDM payload must contain 1..2048 bytes')
    frame = b'SLA1' + struct.pack('!H', len(payload)) + payload
    frame += struct.pack('!I', zlib.crc32(frame))
    bits = np.unpackbits(np.frombuffer(frame, dtype=np.uint8))
    bits = np.pad(bits, (0, (-len(bits)) % len(BINS)))
    data = [symbol(1.0 - 2.0 * row) for row in bits.reshape(-1, len(BINS))]
    output = np.concatenate([PREAMBLE, *data])
    return (output * (0.8 / np.max(np.abs(output)))).astype(np.float32)


def decode(samples):
    values = np.asarray(samples, dtype=np.float64)
    if values.ndim != 1 or not 3 * SYMBOL <= len(values) <= RATE * 10 or not np.all(np.isfinite(values)):
        raise ValueError('Invalid or oversized audio recording')
    # FFT correlation avoids quadratic work for recordings with leading silence.
    n = 1 << (len(values) + len(PREAMBLE) - 2).bit_length()
    correlation = np.fft.irfft(np.fft.rfft(values, n) * np.fft.rfft(PREAMBLE[::-1], n), n)
    valid = correlation[len(PREAMBLE)-1:len(values)]
    energy = np.concatenate(([0.0], np.cumsum(values * values)))
    energy = energy[len(PREAMBLE):] - energy[:-len(PREAMBLE)]
    score = np.abs(valid) / np.sqrt(np.maximum(energy, 1e-20) * np.sum(PREAMBLE * PREAMBLE))
    offset = int(np.argmax(score))
    if score[offset] < 0.6:
        raise ValueError('OFDM preamble not found')
    values = values[offset:]
    available = len(values) // SYMBOL
    blocks = values[:available * SYMBOL].reshape(-1, SYMBOL)[:, PREFIX:]
    carriers = np.fft.fft(blocks, axis=1)[:, BINS]
    channel = np.mean(carriers[:2] / TRAINING, axis=0)
    if np.any(np.abs(channel) < 1e-8):
        raise ValueError('Audio channel has an unusable carrier')
    bits = ((carriers[2:] / channel).real < 0).astype(np.uint8).ravel()
    frame = np.packbits(bits).tobytes()
    if len(frame) < 10 or frame[:4] != b'SLA1':
        raise ValueError('Invalid OFDM header')
    length = struct.unpack('!H', frame[4:6])[0]
    if not 1 <= length <= MAX_PAYLOAD or len(frame) < length + 10:
        raise ValueError('Invalid or truncated OFDM payload')
    end = length + 6
    if zlib.crc32(frame[:end]) != struct.unpack('!I', frame[end:end+4])[0]:
        raise ValueError('Damaged OFDM payload')
    return frame[6:end]


def wav_bytes(samples):
    values = np.asarray(samples)
    if values.ndim != 1 or len(values) > RATE * 10 or not np.all(np.isfinite(values)) or np.max(np.abs(values), initial=0) > 1:
        raise ValueError('Expected bounded normalized mono audio')
    result = io.BytesIO()
    with wave.open(result, 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(RATE)
        output.writeframes(np.rint(values * 32767).astype('<i2').tobytes())
    return result.getvalue()


def read_wav(content):
    if not isinstance(content, bytes) or len(content) > RATE * 20 + 1024:
        raise ValueError('Oversized WAV')
    with wave.open(io.BytesIO(content), 'rb') as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, RATE):
            raise ValueError('Use mono 16-bit PCM at 48 kHz')
        if source.getnframes() > RATE * 10:
            raise ValueError('Oversized recording')
        data = source.readframes(source.getnframes())
        if len(data) != source.getnframes() * 2:
            raise ValueError('Truncated WAV')
    return np.frombuffer(data, dtype='<i2').astype(np.float64) / 32767
