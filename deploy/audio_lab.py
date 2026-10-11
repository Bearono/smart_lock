"""Bounded OFDM key-delivery software experiment; never opens a sound device."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
import numpy as np
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from smartlock_protocol.audio import encode, decode, wav_bytes, read_wav, RATE
from smartlock_protocol.distribution_lab import Recipient, kdc_pair, public_packet
from smartlock_protocol.v2 import b64e, b64d, canonical_json


def run():
    started = time.perf_counter()
    keys = {name: os.urandom(32) for name in ('alice', 'bob')}
    session, tickets = kdc_pair(keys, 'alice', 'bob')
    recovered = [decode(read_wav(wav_bytes(encode(ticket)))) for ticket in tickets]
    first = Recipient('alice').receive_kdc(recovered[0], keys['alice'], 'bob', session)
    second = Recipient('bob').receive_kdc(recovered[1], keys['bob'], 'alice', session)
    issuer = ec.generate_private_key(ec.SECP256R1())
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key = os.urandom(32)
    packet = public_packet('alice', 'bob', private.public_key(), issuer, session, key)
    wire = canonical_json({'binding': packet[0], 'wrapped': b64e(packet[1]), 'signature': b64e(packet[2])})
    samples = encode(wire)
    noise = np.random.default_rng(33).normal(0, 0.001, len(samples))
    channel = np.concatenate((np.zeros(151), (samples + noise) * -0.7))
    data = json.loads(decode(channel))
    delivered = (data['binding'], b64d(data['wrapped']), b64d(data['signature']))
    recipient = Recipient('bob')
    accepted = recipient.receive_public(delivered, private, issuer.public_key(), 'alice', session)
    rejected = False
    try:
        recipient.receive_public(delivered, private, issuer.public_key(), 'alice', session)
    except ValueError:
        rejected = True
    report = {'created_at': datetime.now(timezone.utc).isoformat(),
              'scope': 'software PCM/channel loopback; no microphone, speaker or physical fingerprint validation',
              'passed': first == second and accepted == key and rejected,
              'kdc_key_agrees': first == second, 'signed_rsa_key_agrees': accepted == key,
              'ticket_replay_rejected': rejected, 'sample_rate': RATE,
              'public_packet_bytes': len(wire), 'waveform_seconds': round(len(samples) / RATE, 3),
              'elapsed_seconds': round(time.perf_counter() - started, 3)}
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['passed'] else 1)
