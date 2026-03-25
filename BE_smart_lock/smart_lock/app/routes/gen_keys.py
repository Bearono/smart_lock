from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

# 生成 SECP256R1 曲线的密钥对 (匹配 ECCalgorithm.py)
priv_key = ec.generate_private_key(ec.SECP256R1())
pub_key = priv_key.public_key()

# 保存私钥
with open("backend_priv.pem", "wb") as f:
    f.write(priv_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ))

# 保存公钥
with open("backend_pub.pem", "wb") as f:
    f.write(pub_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ))
