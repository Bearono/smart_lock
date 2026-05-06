"""
MFA系统快速测试脚本
用于验证后端MFA接口是否正常工作
"""

import requests
import json

BASE_URL = "http://localhost:8000"

def test_register_and_login():
    """测试用户注册和登录"""
    print("\n=== 测试1: 用户注册和登录 ===")

    # 注册
    response = requests.post(f"{BASE_URL}/api/register", json={
        "username": "test_user_001",
        "password": "password123"
    })
    print(f"注册: {response.status_code} - {response.json()}")

    # 登录
    response = requests.post(f"{BASE_URL}/api/login", json={
        "username": "test_user_001",
        "password": "password123"
    })
    data = response.json()
    print(f"登录: {response.status_code} - {data}")

    return data.get("access_token")


def test_totp_binding(token):
    """测试TOTP绑定"""
    print("\n=== 测试2: TOTP绑定 ===")

    headers = {"Authorization": f"Bearer {token}"}

    # 绑定TOTP
    response = requests.post(f"{BASE_URL}/api/mfa/bind/totp", headers=headers)
    data = response.json()
    print(f"绑定TOTP: {response.status_code}")
    print(f"密钥: {data.get('secret')}")
    print(f"二维码URI: {data.get('qr_uri')}")
    print(f"凭证ID: {data.get('credential_id')}")

    return data.get("credential_id"), data.get("secret")


def test_device_binding(token):
    """测试设备绑定"""
    print("\n=== 测试3: 设备绑定 ===")

    headers = {"Authorization": f"Bearer {token}"}

    response = requests.post(f"{BASE_URL}/api/mfa/bind/device",
                            headers=headers,
                            json={"device_id": "test_phone_001"})
    print(f"绑定设备: {response.status_code} - {response.json()}")


def test_open_door_request(token):
    """测试开门请求"""
    print("\n=== 测试4: 发起开门请求 ===")

    headers = {"Authorization": f"Bearer {token}"}

    response = requests.post(f"{BASE_URL}/api/mfa/open-door/request",
                            headers=headers,
                            json={"device_id": "test_phone_001"})
    data = response.json()
    print(f"开门请求: {response.status_code}")
    print(f"Request ID: {data.get('request_id')}")
    print(f"Nonce: {data.get('nonce')}")
    print(f"需要人脸: {data.get('requires_face')}")
    print(f"需要TOTP: {data.get('requires_totp')}")

    return data.get("request_id")


def test_face_result(request_id):
    """模拟树莓派上传人脸识别结果"""
    print("\n=== 测试5: 上传人脸识别结果 ===")

    response = requests.post(f"{BASE_URL}/api/mfa/open-door/face-result",
                            json={
                                "request_id": request_id,
                                "device_id": "RPI_LOCK_01",
                                "face_user_id": "test_user_001",
                                "similarity_score": 0.92
                            })
    data = response.json()
    print(f"人脸结果: {response.status_code} - {data}")


def test_confirm_unlock(request_id):
    """测试确认开门"""
    print("\n=== 测试6: 确认开门（获取unlock_token） ===")

    response = requests.post(f"{BASE_URL}/api/mfa/open-door/confirm",
                            json={"request_id": request_id})
    data = response.json()
    print(f"确认开门: {response.status_code}")
    print(f"Unlock Token: {data.get('unlock_token')}")
    print(f"有效期: {data.get('expires_in')}秒")


def test_guest_pass(token):
    """测试访客授权"""
    print("\n=== 测试7: 创建访客授权 ===")

    headers = {"Authorization": f"Bearer {token}"}

    response = requests.post(f"{BASE_URL}/api/mfa/guest/create",
                            headers=headers,
                            json={
                                "guest_name": "访客张三",
                                "valid_from": "2026-05-06T10:00:00",
                                "valid_until": "2026-05-06T18:00:00",
                                "max_uses": 3
                            })
    data = response.json()
    print(f"创建授权: {response.status_code}")
    print(f"授权码: {data.get('pass_code')}")

    return data.get("pass_code")


def test_guest_verify(pass_code):
    """测试访客授权验证"""
    print("\n=== 测试8: 验证访客授权码 ===")

    response = requests.post(f"{BASE_URL}/api/mfa/guest/verify",
                            json={"pass_code": pass_code})
    data = response.json()
    print(f"验证授权: {response.status_code}")
    print(f"Unlock Token: {data.get('unlock_token')}")


def main():
    print("=" * 60)
    print("MFA系统快速测试")
    print("=" * 60)

    try:
        # 1. 注册和登录
        token = test_register_and_login()

        # 2. TOTP绑定
        credential_id, secret = test_totp_binding(token)
        print(f"\n提示: 请使用Google Authenticator扫描二维码或手动输入密钥: {secret}")

        # 3. 设备绑定
        test_device_binding(token)

        # 4. 开门流程
        request_id = test_open_door_request(token)
        test_face_result(request_id)
        test_confirm_unlock(request_id)

        # 5. 访客授权
        pass_code = test_guest_pass(token)
        if pass_code:
            test_guest_verify(pass_code)

        print("\n" + "=" * 60)
        print("测试完成！")
        print("=" * 60)

    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
