"""SLA2 acoustic transport: long guard interval and frequency-diverse repetition.

CRC checks transmission integrity only. Decoded bytes still require authenticated
envelope verification. Work is bounded for a maximum ten-second recording.
"""
import struct
import zlib
import numpy as np
from .audio import RATE, FFT, BINS, TRAINING, MAX_PAYLOAD

PREFIX = FFT
SYMBOL = FFT + PREFIX
DATA_BITS = 21
PROFILE = 'SL-OFDM-2'


def _symbol(carriers):
    spectrum = np.zeros(FFT, dtype=complex)
    spectrum[BINS] = carriers
    spectrum[-BINS] = carriers
    cycle = np.fft.ifft(spectrum).real
    return np.concatenate((cycle, cycle))


PREAMBLE = np.concatenate([_symbol(row) for row in TRAINING])


def encode(payload):
    if not isinstance(payload, bytes) or not 1 <= len(payload) <= MAX_PAYLOAD:
        raise ValueError('OFDM payload must contain 1..2048 bytes')
    packet = b'SLA2' + struct.pack('!H', len(payload)) + payload
    packet += struct.pack('!I', zlib.crc32(packet))
    bits = np.unpackbits(np.frombuffer(packet, dtype=np.uint8))
    bits = np.pad(bits, (0, (-len(bits)) % DATA_BITS)).reshape(-1, DATA_BITS)
    # Each bit occupies three distant carriers. Carrier 79 is reserved, fixed at +1.
    carriers = np.c_[np.tile(1. - 2. * bits, (1, 3)), np.ones(len(bits))]
    output = np.concatenate([PREAMBLE, *[_symbol(row) for row in carriers]])
    return (output * (.8 / np.max(np.abs(output)))).astype(np.float32)


def _carriers(values, offset, count):
    if offset < 0 or offset + count * SYMBOL > len(values):
        raise ValueError('Truncated OFDM frame')
    blocks = values[offset:offset + count * SYMBOL].reshape(-1, SYMBOL)[:, PREFIX:]
    return np.fft.fft(blocks, axis=1)[:, BINS]


def _bytes(carriers, channel):
    # Soft combining weights weak/notched frequencies by their measured gain.
    equalized = carriers[:, :63] * np.conj(channel[:63])
    # Repeated bits cancel in cross-band products. Their phase tracks sampling-clock
    # drift without trusting decoded data or a single potentially notched pilot.
    cross = (equalized[:, DATA_BITS:] * np.conj(equalized[:, :-DATA_BITS])).sum(axis=1)
    phase = np.unwrap(np.angle(cross))
    drift = phase * FFT / (2 * np.pi * DATA_BITS)
    if np.any(abs(drift) > PREFIX / 2):
        raise ValueError('Audio clock drift exceeds the guard interval')
    equalized *= np.exp(-1j * phase[:, None] * BINS[None, :63] / DATA_BITS)
    soft = equalized.real.reshape(-1, 3, DATA_BITS)
    return np.packbits((soft.sum(axis=1) < 0).ravel()).tobytes()


def _decode_at(values, offset):
    carriers = _carriers(values, offset, 5)
    estimates = carriers[:2] / TRAINING
    energy = np.linalg.norm(estimates[0]) * np.linalg.norm(estimates[1])
    coherence = abs(np.vdot(estimates[0], estimates[1])) / max(energy, 1e-20)
    if coherence < .85:
        raise ValueError('Inconsistent OFDM training symbols')
    channel = estimates.mean(axis=0)
    if np.any((abs(channel[:63]) ** 2).reshape(3, DATA_BITS).sum(axis=0) < 1e-16):
        raise ValueError('Audio channel has an unusable carrier group')
    header = _bytes(carriers[2:], channel)
    if header[:4] != b'SLA2':
        raise ValueError('Invalid OFDM header')
    length = struct.unpack('!H', header[4:6])[0]
    if not 1 <= length <= MAX_PAYLOAD:
        raise ValueError('Invalid OFDM payload length')
    count = 2 + (8 * (length + 10) + DATA_BITS - 1) // DATA_BITS
    packet = _bytes(_carriers(values, offset, count)[2:], channel)
    end = length + 6
    if zlib.crc32(packet[:end]) != struct.unpack('!I', packet[end:end + 4])[0]:
        raise ValueError('Damaged OFDM payload')
    return {'payload': packet[6:end], 'channel': channel.copy(), 'start_sample': offset,
            'sample_count': count * SYMBOL, 'training_coherence': float(coherence), 'profile': PROFILE}


def analyze(samples):
    values = np.asarray(samples, dtype=np.float64)
    if values.ndim != 1 or not 5 * SYMBOL <= len(values) <= RATE * 10 or not np.all(np.isfinite(values)):
        raise ValueError('Invalid or oversized audio recording')
    n = 1 << (len(values) + len(PREAMBLE) - 2).bit_length()
    correlation = np.fft.irfft(np.fft.rfft(values, n) * np.fft.rfft(PREAMBLE[::-1], n), n)
    valid = correlation[len(PREAMBLE) - 1:len(values)]
    energy = np.r_[0., np.cumsum(values * values)]
    energy = energy[len(PREAMBLE):] - energy[:-len(PREAMBLE)]
    scores = np.abs(valid) / np.sqrt(np.maximum(energy, 1e-20) * np.sum(PREAMBLE ** 2))
    # Correlation proposes times only; channel consistency, bounds and CRC decide acceptance.
    # Six peaks and nine timing offsets bound noise-only and adversarial decoding work.
    for _ in range(6):
        center = int(np.argmax(scores))
        score = float(scores[center])
        if score < .15:
            break
        scores[max(0, center - 2 * SYMBOL):center + 2 * SYMBOL + 1] = -1
        for delta in (0, -16, 16, -32, 32, -48, 48, -64, 64):
            try:
                return {**_decode_at(values, center + delta), 'sync_score': score}
            except ValueError:
                continue
    raise ValueError('No intact SLA2 acoustic frame found')
