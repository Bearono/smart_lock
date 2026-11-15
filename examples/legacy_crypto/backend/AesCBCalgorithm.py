import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
import random
import string
from flask import Flask

# app=Flask(__name__)
#
# @app.route('/')
# 采用AES对称加密算法,CBC模式


# 使用PKCS7填充,如果长度不为16则补充为16的倍数
def add_to_16(value):
    if isinstance(value, bytes):
        value = value.decode('utf-8')
    padder = padding.PKCS7(128).padder()  # 128位 = 16字节
    paddedData = padder.update(value.encode('utf-8')) + padder.finalize()
    return paddedData


# 移除PKCS7填充
def remove_padding(value):
    unpadder = padding.PKCS7(128).unpadder()
    unpaddedData = unpadder.update(value) + unpadder.finalize()
    return unpaddedData


# 加密方法
def AesEncrypt(data, key):
    iv = b'0000100010010010'
    # 处理输入数据：转换为base64
    if isinstance(data, bytes):
        text = base64.b64encode(data).decode('ascii')
    else:
        text = base64.b64encode(data.encode('utf-8')).decode('ascii')
    cipher = Cipher(algorithms.AES(key.encode('utf-8')), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    # 应用PKCS7填充并加密
    encryptedData = encryptor.update(add_to_16(text)) + encryptor.finalize()

    # 转换为base64字符串
    encryptedText = base64.b64encode(encryptedData).decode('utf-8')
    return encryptedText


# 解密方法
def AesDecrypt(encryptedText, key):
    iv = b'0000100010010010'
    cipher = Cipher(algorithms.AES(key.encode('utf-8')), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()

    # Base64解码并解密
    encryptedData = base64.b64decode(encryptedText)
    decryptedPadded = decryptor.update(encryptedData) + decryptor.finalize()

    # 移除填充
    decryptedText = remove_padding(decryptedPadded).decode('utf-8')

    # Base64解码返回原始图片数据
    originalData = base64.b64decode(decryptedText)
    return originalData

#生成AES加密密钥
def genKey():
    source = string.ascii_letters + string.digits
    key = "".join(random.sample(source, 16))
    return key


# if __name__ == '__main__':
#     app.run(host='0.0.0.0',port=8080,debug=True)