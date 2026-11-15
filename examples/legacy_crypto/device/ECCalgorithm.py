from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.backends import default_backend


# 1. 生成 ECC 密钥对 (比 RSA 快得多)
def generate_ecc_keys():
    # 用于签名的 Key (Ed25519)
    sign_priv = ed25519.Ed25519PrivateKey.generate()
    sign_pub = sign_priv.public_key()

    # 用于加密的 Key (SECP256R1 / NIST P-256)
    # 注意：Ed25519只能签名，不能加密，所以加密要用另一条曲线
    enc_priv = ec.generate_private_key(ec.SECP256R1(), default_backend())
    enc_pub = enc_priv.public_key()

    # 序列化私钥 (保存到磁盘)
    sign_pem = sign_priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    # ... 省略了保存逻辑，和RSA类似
    return sign_priv, enc_pub  # 仅演示返回对象


# 2. 极速签名 (Ed25519)
def sign_data_fast(private_key, data: bytes) -> bytes:
    # Ed25519 不需要哈希预处理，它内部处理了，直接签
    return private_key.sign(data)


# 3. 验证签名
def verify_data_fast(public_key, data: bytes, signature: bytes) -> bool:
    try:
        public_key.verify(signature, data)
        return True
    except:
        return False

# === 新增：轻量级加密 AES Key (发送端调用) ===
def encrypt_aes_key_ecc(aes_key: bytes, receiver_pub_key):
    # 1. 搞个临时的私钥 (Ephemeral Key)
    tmp_priv = ec.generate_private_key(ec.SECP256R1(), default_backend())

    # 2. ECDH 协议协商共享密钥
    shared_secret = tmp_priv.exchange(ec.ECDH(), receiver_pub_key)

    # 3. 派生密钥 (HKDF)
    derived_k = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b'handshake',  # 这个info两边要一样
        backend=default_backend()
    ).derive(shared_secret)

    # 4. 异或加密 (简单高效)
    # 实际 AES key 通常是 16 字节
    enc_k = bytes([a ^ b for a, b in zip(aes_key, derived_k[:len(aes_key)])])

    # 5. 把临时公钥导出来，发给对面
    tmp_pub_bytes = tmp_priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    # 用 ||| 分隔公钥和密文，方便对面拆解
    return tmp_pub_bytes + b"|||" + enc_k


# === 新增：解密 AES Key (接收端调用) ===
def decrypt_aes_key_ecc(blob: bytes, receiver_priv_key):
    try:
        # 1. 拆包：分出临时公钥和密文
        parts = blob.split(b"|||")
        if len(parts) != 2:
            return None

        peer_pub_bytes = parts[0]
        encrypted_k = parts[1]

        # 2. 加载对方发来的临时公钥
        peer_pub = serialization.load_pem_public_key(
            peer_pub_bytes,
            backend=default_backend()
        )

        # 3. 同样的 ECDH 协商 (拿到一模一样的 shared_secret)
        shared_secret = receiver_priv_key.exchange(ec.ECDH(), peer_pub)

        # 4. 同样的 HKDF 派生
        derived_k = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b'handshake',
            backend=default_backend()
        ).derive(shared_secret)

        # 5. 异或解密 (XOR 是可逆的：A^B^B = A)
        original_aes_key = bytes([a ^ b for a, b in zip(encrypted_k, derived_k[:len(encrypted_k)])])

        return original_aes_key.decode('utf-8')  # 假设你的 genKey 返回的是字符串
    except Exception as e:
        print(f"ECC Decrypt error: {e}")
        return None