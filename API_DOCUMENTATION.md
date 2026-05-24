# 智能锁后端接口文档

后端默认地址：

```text
http://<后端IP>:8000
```

需要登录态的接口请在请求头携带 JWT：

```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

## 1. 用户注册

```http
POST /api/register
```

请求：

```json
{
  "username": "alice",
  "password": "123456"
}
```

成功响应 `201`：

```json
{
  "msg": "Registered successfully"
}
```

常见错误：

```json
{
  "msg": "User exists"
}
```

## 2. 用户登录

```http
POST /api/login
```

请求：

```json
{
  "username": "alice",
  "password": "123456"
}
```

成功响应 `200`：

```json
{
  "access_token": "jwt-token-string"
}
```

失败响应 `401`：

```json
{
  "msg": "Invalid credentials"
}
```

## 3. 查询门锁状态

需要 JWT。

```http
GET /api/lock/status?device_id=door_01
```

`device_id` 可选，默认 `door_01`。

成功响应：

```json
{
  "device_id": "door_01",
  "status": "LOCKED",
  "battery": 90,
  "last_update": "2026-05-23 15:20:00"
}
```

`status` 可能值：

```text
LOCKED
UNLOCKED
```

## 4. 控制门锁

需要 JWT。

```http
POST /api/lock/control
```

请求：

```json
{
  "device_id": "door_01",
  "action": "UNLOCK"
}
```

`action` 可选值：

```text
LOCK
UNLOCK
```

成功响应：

```json
{
  "status": "success",
  "msg": "指令已下发并更新状态",
  "new_status": "UNLOCK"
}
```

## 5. 获取开锁历史

需要 JWT。

```http
GET /api/lock/history?page=1&per_page=10
```

成功响应：

```json
{
  "total": 25,
  "pages": 3,
  "current_page": 1,
  "data": [
    {
      "id": 1,
      "username": "alice",
      "action": "UNLOCK",
      "timestamp": "2026-05-23 15:20:00"
    }
  ]
}
```

## 6. 绑定 TOTP

需要 JWT。

```http
POST /api/mfa/bind/totp
```

请求：

```json
{}
```

成功响应：

```json
{
  "msg": "TOTP secret generated",
  "secret": "BASE32SECRET",
  "qr_uri": "otpauth://totp/SmartLock:alice?secret=BASE32SECRET&issuer=SmartLock",
  "credential_id": 1
}
```

前端可以使用 `qr_uri` 生成二维码，让用户用认证器 App 扫码。

## 7. 验证 TOTP

需要 JWT。

```http
POST /api/mfa/verify/totp
```

绑定确认场景：

```json
{
  "credential_id": 1,
  "code": "123456"
}
```

成功响应：

```json
{
  "msg": "TOTP bound successfully"
}
```

普通验证场景：

```json
{
  "code": "123456"
}
```

成功响应：

```json
{
  "msg": "TOTP verified"
}
```

## 8. 绑定设备

需要 JWT。

```http
POST /api/mfa/bind/device
```

请求：

```json
{
  "device_id": "RPI_LOCK_01",
  "device_pubkey": "optional-public-key"
}
```

成功响应：

```json
{
  "msg": "Device bound successfully"
}
```

## 9. 查询 MFA 状态

需要 JWT。

```http
GET /api/mfa/status
```

成功响应：

```json
{
  "totp_bound": true,
  "devices": [
    {
      "credential_id": 1,
      "device_id": "RPI_LOCK_01",
      "is_active": true,
      "created_at": "2026-05-23 15:20:00"
    }
  ]
}
```

## 10. 解绑 TOTP

需要 JWT。

```http
POST /api/mfa/unbind/totp
```

成功响应：

```json
{
  "msg": "TOTP unbound successfully"
}
```

## 11. 解绑设备

需要 JWT。

```http
POST /api/mfa/unbind/device
```

请求：

```json
{
  "device_id": "RPI_LOCK_01"
}
```

成功响应：

```json
{
  "msg": "Device unbound successfully"
}
```

## 12. 发起开门认证

需要 JWT。

```http
POST /api/mfa/open-door/request
```

请求：

```json
{
  "device_id": "RPI_LOCK_01"
}
```

成功响应：

```json
{
  "msg": "Auth session created",
  "request_id": "request-id-string",
  "nonce": "nonce-string",
  "requires_face": true,
  "requires_totp": false
}
```

若该用户绑定的设备因连续 5 次认证失败被锁定，接口将返回 423：

失败响应: 423 (设备已被安全锁定)：
```json
{
  "msg": "Device is LOCKED due to multiple failed attempts. Please contact Administrator.",
  "code": "DEVICE_LOCKED"
}
```
前端拿到 `request_id` 后，等待树莓派或摄像头侧完成人脸识别上传。

## 13. 确认开门

需要 JWT。

```http
POST /api/mfa/open-door/confirm
```

不需要 TOTP 时：

```json
{
  "request_id": "request-id-string"
}
```

需要 TOTP 时：

```json
{
  "request_id": "request-id-string",
  "totp_code": "123456"
}
```

成功响应：

```json
{
  "msg": "Authentication successful",
  "unlock_token": "unlock-token-string",
  "expires_in": 60
}
```

失败或未完成：

```json
{
  "msg": "Authentication incomplete"
}
```

## 14. 消费开门令牌

通常给硬件端调用。用于消费 `/api/mfa/open-door/confirm` 或 `/api/mfa/guest/verify` 返回的 `unlock_token`。

```http
POST /api/lock/unlock-token/verify
```

请求：

```json
{
  "device_id": "RPI_LOCK_01",
  "unlock_token": "unlock-token-string"
}
```

成功响应：

```json
{
  "msg": "Unlock token accepted",
  "device_id": "RPI_LOCK_01",
  "new_status": "UNLOCKED"
}
```

常见错误：

```json
{
  "msg": "Unlock token expired"
}
```

## 15. 管理员解除设备锁定

需要 JWT

```http
POST /api/mfa/admin/device/unlock
```

请求：

```json

{
  "target_username": "alice"
}
```
成功响应 200

```json

{
  "msg": "Device for alice has been successfully unlocked."
}
```

## 16. 创建设备心跳

通常给树莓派端调用，不需要 JWT。

```http
POST /api/device/heartbeat
```

请求：

```json
{
  "device_id": "RPI_LOCK_01",
  "battery": 86,
  "camera_status": "OK",
  "lock_status": "LOCKED",
  "ip": "192.168.1.20"
}
```

成功响应：

```json
{
  "msg": "Heartbeat received",
  "device": {
    "device_id": "RPI_LOCK_01",
    "status": "LOCKED",
    "battery": 86,
    "camera_status": "OK",
    "ip_address": "192.168.1.20",
    "is_online": true,
    "last_update": "2026-05-23 15:20:00"
  }
}
```

## 17. 查询设备在线状态

需要 JWT。

```http
GET /api/device/status
GET /api/device/status?device_id=RPI_LOCK_01
```

不传 `device_id` 时返回设备列表；传入时返回单个设备。

成功响应：

```json
{
  "device_id": "RPI_LOCK_01",
  "status": "LOCKED",
  "battery": 86,
  "camera_status": "OK",
  "ip_address": "192.168.1.20",
  "is_online": true,
  "last_update": "2026-05-23 15:20:00"
}
```

## 18. 查询人脸识别记录

需要 JWT。

```http
GET /api/face/logs?page=1&per_page=10
GET /api/face/logs?passed=false
GET /api/face/logs?device_id=RPI_LOCK_01
```

成功响应：

```json
{
  "total": 25,
  "pages": 3,
  "current_page": 1,
  "data": [
    {
      "id": 1,
      "request_id": "request-id-string",
      "device_id": "RPI_LOCK_01",
      "expected_username": "alice",
      "face_user_id": "alice",
      "similarity_score": 0.92,
      "passed": true,
      "snapshot": "/static/captures/face_123.jpg",
      "failure_reason": null,
      "timestamp": "2026-05-23 15:20:00"
    }
  ]
}
```

## 19. 创建访客授权码

需要 JWT。

```http
POST /api/mfa/guest/create
```

请求：

```json
{
  "guest_name": "Bob",
  "valid_hours": 24,
  "max_uses": 1
}
```

成功响应：

```json
{
  "msg": "Guest pass created",
  "pass_code": "plain-pass-code",
  "valid_until": "2026-05-24T15:20:00",
  "max_uses": 1
}
```

注意：`pass_code` 明文只返回这一次，前端需要当场展示或复制。

## 20. 查询访客授权列表

需要 JWT。

```http
GET /api/mfa/guest/list
```

成功响应：

```json
[
  {
    "id": 1,
    "guest_name": "Bob",
    "valid_from": "2026-05-23T15:20:00",
    "valid_until": "2026-05-24T15:20:00",
    "max_uses": 1,
    "used_count": 0,
    "is_active": true,
    "created_at": "2026-05-23 15:20:00"
  }
]
```

## 21. 验证访客授权码

不需要 JWT。

```http
POST /api/mfa/guest/verify
```

请求：

```json
{
  "pass_code": "plain-pass-code"
}
```

成功响应：

```json
{
  "msg": "Guest pass verified",
  "unlock_token": "unlock-token-string",
  "expires_in": 60
}
```

## 22. 撤销访客授权

需要 JWT。

```http
POST /api/mfa/guest/revoke/{pass_id}
```

示例：

```http
POST /api/mfa/guest/revoke/1
```

成功响应：

```json
{
  "msg": "Guest pass revoked"
}
```

## 23. 获取报警记录

```http
GET /api/alarms
GET /api/alarms?status=pending&limit=20
```

成功响应：

```json
[
  {
    "id": 1,
    "time": "2026-05-23 15:20:00",
    "type": "异常开门",
    "message": "检测到异常",
    "snapshot": "/static/captures/alarm_123.jpg",
    "status": "pending",
    "handled_by": null,
    "handled_at": null
  }
]
```

`snapshot` 如果不是图片路径，可能是 `无画面` 一类文本。

## 24. 处理报警

需要 JWT。

```http
PATCH /api/alarms/{alarm_id}
```

请求：

```json
{
  "status": "resolved"
}
```

`status` 可选值：

```text
pending
resolved
ignored
```

成功响应：

```json
{
  "id": 1,
  "time": "2026-05-23 15:20:00",
  "type": "异常开门",
  "message": "检测到异常",
  "snapshot": "/static/captures/alarm_123.jpg",
  "status": "resolved",
  "handled_by": "alice",
  "handled_at": "2026-05-23 15:30:00"
}
```

## 25. 触发报警

通常给硬件或后端内部使用，前端如需测试也可以调用。

```http
POST /api/trigger_alarm
```

请求：

```json
{
  "type": "异常开门",
  "message": "检测到异常"
}
```

成功响应：

```json
{
  "status": "success",
  "snapshot": "/static/captures/alarm_123.jpg"
}
```

## 26. 实时视频流

用于页面 `<img>` 或视频预览。

```http
GET /video_feed
```

前端示例：

```html
<img src="http://<后端IP>:8000/video_feed" />
```

返回类型：

```text
multipart/x-mixed-replace; boundary=frame
```

## 27. 监控后台页面

后端内置 HTML 页面：

```http
GET /
```

主要用于简单调试，不一定需要前端集成。

## 前端推荐流程

普通账号登录：

```text
注册 /api/register
登录 /api/login
保存 access_token
查询门锁状态 /api/lock/status
控制门锁 /api/lock/control
查看历史 /api/lock/history
```

MFA 开门流程：

```text
登录
绑定设备 /api/mfa/bind/device
查询 MFA 状态 /api/mfa/status
可选绑定 TOTP /api/mfa/bind/totp -> /api/mfa/verify/totp
发起开门 /api/mfa/open-door/request
等待人脸识别完成
确认开门 /api/mfa/open-door/confirm
拿到 unlock_token
硬件消费令牌 /api/lock/unlock-token/verify
```

访客流程：

```text
主人登录
创建访客码 /api/mfa/guest/create
查看访客码列表 /api/mfa/guest/list
访客提交授权码 /api/mfa/guest/verify
拿到 unlock_token
硬件消费令牌 /api/lock/unlock-token/verify
```

摄像头与安全中心：

```text
树莓派定时上报 /api/device/heartbeat
前端查看设备状态 /api/device/status
前端查看人脸识别记录 /api/face/logs
前端查看报警 /api/alarms
前端处理报警 /api/alarms/{alarm_id}
```
设备锁定与异常处理（防暴力破解）：

```text
发起开门 /api/mfa/open-door/request 
若连续5次认证失败，服务端触发锁定，返回 423 DEVICE_LOCKED
前端捕获 423 状态，弹窗提示：“设备已锁定，请联系管理员”
管理员登录后台，调用 /api/mfa/admin/device/unlock 解锁
设备恢复正常认证流程
```

---

## 16. SPAKE2 安全握手接口

该接口用于树莓派/硬件端与后端建立短期安全会话。后续 `/api/secure/upload`、`/api/mfa/open-door/face-result`、`/api/mfa/open-door/confirm` 等硬件端上报接口可使用本接口协商出的 `session_key` 进行 AES-CBC 加密和 HMAC-SHA256 完整性校验。

```http
POST /api/security/spake2/start
```

请求：

```json
{
  "version": "SL-SEC-v2",
  "device_id": "RPI_LOCK_01",
  "client_pub": "base64-spake2-a-message",
  "client_nonce": "base64-client-nonce",
  "timestamp": 1710000000,
  "request_id": "unique-request-id"
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| `version` | 安全协议版本，当前为 `SL-SEC-v2` |
| `device_id` | 设备编号，用于绑定安全会话 |
| `client_pub` | 设备端 `SPAKE2_A.start()` 生成的消息，Base64 编码；字段名保留为 `client_pub` 以兼容旧接口命名 |
| `client_nonce` | 设备端随机数，Base64 编码 |
| `timestamp` | 请求时间戳，用于防止过期握手请求 |
| `request_id` | 本次握手请求唯一标识 |

成功响应 `200`：

```json
{
  "version": "SL-SEC-v2",
  "session_id": "session-id",
  "server_pub": "base64-spake2-b-message",
  "server_nonce": "base64-server-nonce",
  "challenge": "base64-hmac-challenge",
  "expires_at": 1710000300.0
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| `session_id` | 后端生成的安全会话 ID |
| `server_pub` | 后端 `SPAKE2_B.start()` 生成的消息，Base64 编码；字段名保留为 `server_pub` 以兼容旧接口命名 |
| `server_nonce` | 后端随机数，Base64 编码 |
| `challenge` | 后端基于 `session_key` 生成的 HMAC 挑战值，设备端用于验证握手成功 |
| `expires_at` | 会话过期时间戳 |

常见错误：

```json
{
  "msg": "Invalid SPAKE2 start message"
}
```

```json
{
  "msg": "SPAKE2 start message expired"
}
```

```json
{
  "msg": "Invalid SPAKE2 message or nonce",
  "detail": "..."
}
```

## 17. 查询安全会话状态

该接口用于调试或演示安全会话是否仍然有效。

```http
GET /api/security/session/<session_id>
```

成功响应 `200`：

```json
{
  "active": true,
  "device_id": "RPI_LOCK_01",
  "expires_at": 1710000300.0
}
```

会话不存在或已过期响应 `404`：

```json
{
  "active": false
}
```

## 18. v2 安全包格式说明

硬件端通过 SPAKE2 握手得到 `session_key` 后，业务数据会被封装为 v2 安全包再发送到原有业务接口。例如 `/api/secure/upload` 仍是原接口，但请求体从旧版 `enc_key + payload` 扩展为如下格式：

```json
{
  "header": {
    "version": "SL-SEC-v2",
    "session_id": "session-id",
    "device_id": "RPI_LOCK_01",
    "timestamp": 1710000000,
    "request_id": "unique-request-id",
    "nonce": "base64-random-nonce",
    "unlock_token": "optional-token"
  },
  "iv": "base64-aes-cbc-iv",
  "ciphertext": "base64-ciphertext",
  "mac": "base64-hmac-sha256"
}
```

后端处理顺序：先校验 `version`、`timestamp`、`request_id`、`nonce`、`session_id`、`device_id` 和 `mac`，通过后才使用 AES-CBC 解密 `ciphertext`。旧版 `enc_key + payload` 格式仍保留兼容。
