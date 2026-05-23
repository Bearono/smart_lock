import base64
import json
from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

from .AesCBCalgorithm import AesDecrypt
from .ECCalgorithm import decrypt_aes_key_ecc


PRIVATE_KEY_PATH = Path(__file__).resolve().parents[2] / "backend_priv.pem"


def load_private_key():
    with PRIVATE_KEY_PATH.open("rb") as key_file:
        return serialization.load_pem_private_key(
            key_file.read(),
            password=None,
            backend=default_backend(),
        )


PRIVATE_KEY = load_private_key()


def decrypt_secure_payload(packet):
    enc_key = packet.get("enc_key")
    payload = packet.get("payload")
    if not enc_key or not payload:
        raise ValueError("Missing encrypted payload fields")

    enc_key_bytes = base64.b64decode(enc_key)
    aes_key = decrypt_aes_key_ecc(enc_key_bytes, PRIVATE_KEY)
    if not aes_key:
        raise ValueError("Failed to decrypt AES key")
    if isinstance(aes_key, bytes):
        aes_key = aes_key.decode("utf-8")

    decrypted_json_bytes = AesDecrypt(payload, aes_key)
    return json.loads(decrypted_json_bytes.decode("utf-8"))
