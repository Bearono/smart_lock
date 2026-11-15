"""Explicitly enrolled acoustic-path measurements for the course experiment.

These features include speaker, microphone and room effects. They are not a
cryptographic identity, liveness proof or permission to operate a lock. Enrolment,
calibration and evaluation must use separate recordings from consenting devices.
"""
import hashlib
import math
import re

import numpy as np

from .audio import BINS, FFT, RATE, analyze, read_wav

VERSION = 'SL-acoustic-path-v2'


def extract(recording, expected_payload=None):
    samples = read_wav(recording)
    result = analyze(samples)
    frame = samples[result['start_sample']:result['start_sample'] + result['sample_count']]
    if np.mean(np.abs(frame) >= 0.999) > 0.001:
        raise ValueError('Clipped recording; reduce playback volume or input gain')
    if expected_payload is not None and result['payload'] != expected_payload:
        raise ValueError('Recording does not contain the expected challenge')
    magnitude = np.abs(result['channel'])
    response = 20 * np.log10(np.maximum(magnitude, 1e-12))
    response -= np.mean(response)
    # Bind trial identity to decoded PCM, so RIFF metadata cannot disguise reuse.
    pcm = np.rint(samples * 32767).astype('<i2').tobytes()
    return {'feature': response.tolist(),
            'transport_profile': result['profile'],
            'recording_sha256': hashlib.sha256(pcm).hexdigest(),
            'source_file_sha256': hashlib.sha256(recording).hexdigest(),
            'payload_sha256': hashlib.sha256(result['payload']).hexdigest(),
            'sync_score': result['sync_score'], 'start_sample': result['start_sample']}


def _vectors(records, minimum):
    if not isinstance(records, list) or len(records) < minimum or len(records) > 1000:
        raise ValueError(f'Use {minimum}..1000 separately collected recordings')
    identifiers = [r['recording_sha256'] for r in records]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError('Duplicate recordings are not independent trials')
    if len({r['transport_profile'] for r in records}) != 1:
        raise ValueError('Acoustic trials must use one transport profile')
    matrix = np.asarray([r['feature'] for r in records], dtype=float)
    if matrix.shape != (len(records), len(BINS)) or not np.all(np.isfinite(matrix)):
        raise ValueError('Invalid acoustic feature vectors')
    return matrix, identifiers


def enroll(device_id, recordings):
    if not isinstance(device_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,50}', device_id):
        raise ValueError('Invalid device identity')
    records = [extract(item) for item in recordings]
    matrix, identifiers = _vectors(records, 3)
    return {'version': VERSION, 'device_id': device_id,
            'transport_profile': records[0]['transport_profile'],
            'scope': 'speaker-microphone-room path; not a stand-alone authenticator',
            'sample_rate': RATE, 'frequencies_hz': (BINS * RATE / FFT).tolist(),
            'recording_hash_kind': 'decoded-pcm-s16le',
            'center_db': np.mean(matrix, axis=0).tolist(),
            'scale_db': np.maximum(np.std(matrix, axis=0, ddof=1), 0.75).tolist(),
            'enrollment_sha256': identifiers, 'threshold': None,
            'calibration': None}


def distance(template, feature):
    if (template.get('version') != VERSION or template.get('sample_rate') != RATE
            or template.get('transport_profile') not in ('SL-OFDM-1', 'SL-OFDM-2')):
        raise ValueError('Unsupported acoustic template')
    center, scale, value = (np.asarray(x, dtype=float) for x in
                            (template['center_db'], template['scale_db'], feature))
    if any(x.shape != (len(BINS),) or not np.all(np.isfinite(x)) for x in (center, scale, value)):
        raise ValueError('Invalid template or features')
    if np.any(scale < 0.75):
        raise ValueError('Invalid feature scale')
    return float(np.sqrt(np.mean(((value - center) / scale) ** 2)))


def _scored(template, recordings, minimum=3):
    records = [extract(item) for item in recordings]
    _, identifiers = _vectors(records, minimum)
    if any(r['transport_profile'] != template.get('transport_profile') for r in records):
        raise ValueError('Acoustic transport profile does not match enrollment')
    return [distance(template, record['feature']) for record in records], identifiers


def _separate(*groups):
    all_ids = [value for group in groups for value in group]
    if len(set(all_ids)) != len(all_ids):
        raise ValueError('Enrollment, calibration and evaluation recordings must be disjoint')


def calibrate(template, genuine, impostor, target_far=0.0):
    if type(target_far) not in (int, float) or not math.isfinite(target_far) or not 0 <= target_far <= 0.2:
        raise ValueError('Target FAR must be between 0 and 0.2')
    positive, p_ids = _scored(template, genuine)
    negative, n_ids = _scored(template, impostor)
    _separate(template['enrollment_sha256'], p_ids, n_ids)
    candidates = sorted(set(positive + [float(np.nextafter(v, -math.inf)) for v in negative]))
    candidates = [v for v in candidates if v >= 0 and sum(x <= v for x in negative) / len(negative) <= target_far]
    if not candidates:
        raise ValueError('No threshold satisfies the calibration FAR target')
    boundary = max(candidates)
    # Keep a margin from the nearest rejected calibration sample instead of placing
    # the threshold one floating-point step below it (which overfits tiny noise).
    accepted_positive = [value for value in positive if value <= boundary]
    if not accepted_positive:
        raise ValueError('Calibration rejects every genuine recording; recollect or improve features')
    lower = max(accepted_positive)
    rejected_negative = [value for value in negative if value > boundary]
    threshold = (lower + min(rejected_negative)) / 2 if rejected_negative else lower
    accepted = sum(value <= threshold for value in positive)
    if not accepted:
        raise ValueError('Calibration rejects every genuine recording; recollect or improve features')
    result = dict(template)
    result['threshold'] = threshold
    result['calibration'] = {
        'genuine_count': len(positive), 'impostor_count': len(negative),
        'target_far': float(target_far),
        'far': sum(value <= threshold for value in negative) / len(negative),
        'frr': 1 - accepted / len(positive),
        'genuine_distances': positive, 'impostor_distances': negative,
        'recording_sha256': p_ids + n_ids,
        'scope': 'threshold-selection set; not independent test accuracy'}
    return result


def verify(template, recording, expected_payload=None):
    threshold = template.get('threshold')
    if type(threshold) not in (int, float) or not math.isfinite(threshold) or threshold < 0 or not template.get('calibration'):
        raise ValueError('Calibrate with independent genuine and impostor recordings before verification')
    record = extract(recording, expected_payload)
    if record['transport_profile'] != template.get('transport_profile'):
        raise ValueError('Acoustic transport profile does not match enrollment')
    score = distance(template, record['feature'])
    return {'device_id': template['device_id'], 'distance': score, 'threshold': threshold,
            'matched': score <= threshold, 'recording_sha256': record['recording_sha256'],
            'sync_score': record['sync_score'], 'cryptographic_identity_verified': False}


def evaluate(template, genuine, impostor):
    positive, p_ids = _scored(template, genuine)
    negative, n_ids = _scored(template, impostor)
    calibration = template.get('calibration')
    if not calibration:
        raise ValueError('Missing calibration')
    _separate(template['enrollment_sha256'], calibration['recording_sha256'], p_ids, n_ids)
    threshold = template.get('threshold')
    if type(threshold) not in (int, float) or not math.isfinite(threshold) or threshold < 0:
        raise ValueError('Invalid calibrated threshold')
    fa, fr = sum(v <= threshold for v in negative), sum(v > threshold for v in positive)
    return {'version': VERSION, 'device_id': template['device_id'], 'threshold': threshold,
            'genuine_count': len(positive), 'impostor_count': len(negative),
            'false_accepts': fa, 'false_rejects': fr,
            'far': fa / len(negative), 'frr': fr / len(positive),
            'genuine_distances': positive, 'impostor_distances': negative,
            'recording_sha256': p_ids + n_ids,
            'scope': 'independent recordings; operator must record devices, room and attack types'}
