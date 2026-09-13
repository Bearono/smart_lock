# 智能门锁 API

后端默认 `http://localhost:8000`。请求体使用 JSON。除注明公开或设备接口外，携带 `Authorization: Bearer <access_token>`；JWT 必须由完成 TOTP 的登录流程签发，账号必须处于 approved 且仍有有效 TOTP 凭证。

## 登录与管理员

| 接口 | 请求 / 说明 |
| --- | --- |
| `POST /api/register` | `{username, password}`；201，账号 pending |
| `POST /api/login/pre` | `{username, password}`；200，返回登录挑战 |
| `POST /api/login` | 与 `/login/pre` 完全相同，不再直接签发 JWT |
| `POST /api/login/mfa/bind` | `{pre_token, code}`；首次绑定，返回 `{access_token, role}` |
| `POST /api/login/mfa/verify` | `{pre_token, code}`；已绑定用户登录，返回 `{access_token, role}` |
| `GET /api/admin/users?status=pending` | 管理员查询用户 |
| `GET /api/admin/users/pending` | 管理员查询待审批用户 |
| `POST /api/admin/users/<id>/approve` | 管理员批准 |
| `POST /api/admin/users/<id>/reject` | 管理员驳回，后续受保护请求立即拒绝 |

登录挑战响应含 `pre_token`、`totp_bound`、`role`、`msg`。首次绑定另含 `secret`、`qr_uri`、`credential_id`。挑战 5 分钟有效，最多 5 次验证码尝试；成功后只能消费一次。返回 `restart_login=true` 时重新输入账号密码。临时挑战存数据库，可跨后端进程处理。

## TOTP 与设备绑定

| 接口 | 请求 / 说明 |
| --- | --- |
| `GET /api/mfa/status` | 返回 `{totp_bound, devices}` |
| `POST /api/mfa/bind/totp` | 生成待激活凭证，返回 `{secret, qr_uri, credential_id}` |
| `POST /api/mfa/verify/totp` | `{code, credential_id?}`；验证或激活 TOTP |
| `POST /api/mfa/unbind/totp` | 解绑；之后须重新走首次登录绑定 |
| `POST /api/mfa/bind/device` | `{device_id, device_pubkey?}`；恢复绑定不清除安全锁定 |
| `POST /api/mfa/unbind/device` | `{device_id}`；同时作废该用户该设备的认证、令牌及访客授权 |
| `POST /api/mfa/admin/device/unlock` | 管理员提交 `{target_username}`，清除该用户设备绑定的安全锁定 |

## 完整开门流程

### 1. 发起认证

`POST /api/mfa/open-door/request`，JWT，`{device_id}`。

响应：`{request_id, nonce, requires_face, requires_totp, device_dispatch}`。会话有效期 5 分钟，绑定指定设备。夜间创建的会话要求 TOTP，策略在该会话内固定。未绑定返回 403；安全锁定返回 423；设备派发失败返回 502。

默认要求设备派发成功。显式设置 `DEVICE_DISPATCH_REQUIRED=false` 后，连接失败/超时返回 200 和 `device_dispatch.status="pending"`，等待测试设备的合法加密上报；不会设置 `face_verified=true`。其他设备错误仍返回 502。

### 2. 人脸结果（设备 v2 加密接口）

`POST /api/mfa/open-door/face-result`，请求体必须是下述 v2 信封。解密业务内容：

```json
{
  "request_id": "第一步的request_id",
  "device_id": "door_01",
  "session_nonce": "第一步的nonce",
  "face_user_id": "alice",
  "similarity_score": 0.95
}
```

可选 `snapshot_image`（Base64 JPEG）。业务设备必须与安全会话及开门认证设备一致。明文上报 401，MAC/重放错误 400，错误设备 403，过期会话 410，已处理会话 400/409。用户名匹配且有限数值相似度 ≥ 0.90 才通过。该阈值是项目配置选择，不代表已测得的误识率或活体保证。

### 3. 确认认证

`POST /api/mfa/open-door/confirm`，JWT，`{request_id, totp_code?}`。

成功返回 `{unlock_token, device_id, expires_in: 60}`。会话只能签发一次，重复或并发重复确认返回 409；过期返回 410；缺少人脸或认证失败返回 401；所需 TOTP 未提供返回 400。签发时尚未改变门锁目标状态。

### 4. 消费令牌

`POST /api/lock/unlock-token/verify`，无需 JWT，凭令牌授权：

```json
{"device_id":"door_01","unlock_token":"第三步返回的令牌"}
```

成功返回：

```json
{
  "msg": "Unlock token accepted",
  "device_id": "door_01",
  "new_status": "UNLOCKED",
  "command_accepted": true,
  "hardware_confirmed": false
}
```

消费与目标状态更新在同一事务中完成。令牌过期、已使用返回 401/409；错误设备或授权撤销返回 403。令牌是敏感的短期持有凭证，不写入日志或持久化前端存储。

**这表示指令已被后端接受，不表示物理门锁已打开。** 当前代码没有 GPIO 驱动或命令级硬件回执。前端只在消费成功后显示指令已接受，网络失败可重试消费；若第一次已在后端成功但响应丢失，重试会报令牌已使用，应查询状态，不能推断硬件执行成功。

`POST /api/lock/control` 仅允许 JWT 用户对已绑定设备发送 `{device_id, action:"LOCK"}`。`UNLOCK` 固定返回 403 `MFA_REQUIRED`，管理员也不能绕过。

## 访客授权

| 接口 | 请求 / 说明 |
| --- | --- |
| `POST /api/mfa/guest/create` | JWT；`{device_id, guest_name?, valid_hours:24, max_uses:1}`，必须绑定设备。小时范围 1–168，次数 1–100 |
| `GET /api/mfa/guest/list` | JWT；当前用户创建的授权列表，包含 device_id |
| `POST /api/mfa/guest/verify` | 公开；`{pass_code}`，返回绑定设备的 `{unlock_token, device_id, expires_in}` |
| `POST /api/mfa/guest/revoke/<id>` | JWT；撤销自己的授权，未消费的访客令牌也失效 |

授权码明文只在创建时返回，数据库保存其摘要。验证时原子扣减可签发次数；失败消费不会自动退还。页面会保留未成功消费的令牌用于网络重试，不会再次验证访客码消耗额外次数。访客也必须完成上述第四步，不能把签发令牌当作已开门。

## SPAKE2 与安全信封

设备调用 `POST /api/security/spake2/start`：

```json
{"version":"SL-SEC-v2","device_id":"door_01","client_pub":"Base64 SPAKE2_A消息","client_nonce":"Base64随机数","timestamp":1780000000,"request_id":"唯一ID"}
```

响应含 `session_id`、`server_pub`、`server_nonce`、`challenge`、`expires_at` 和 `version`。客户端计算共享密钥并验证 challenge。业务信封：

```json
{
  "header": {
    "version":"SL-SEC-v2", "session_id":"...", "device_id":"door_01",
    "timestamp":1780000000, "request_id":"本条消息唯一ID", "nonce":"Base64随机数"
  },
  "iv":"Base64 IV", "ciphertext":"Base64 AES-CBC密文", "mac":"Base64 HMAC-SHA256"
}
```

信封 request_id 与业务开门 request_id 用途不同；业务内容可携带原开门 request_id。时间戳必须为整数，nonce/IV 为 16 字节，MAC 为 32 字节，Base64 必须使用标准规范编码，业务 JSON 不接受 NaN/Infinity。后端先核对时间、会话、设备和 MAC，再解密。所有检查通过后，原子保存防重放记录，再执行业务操作；业务失败也不能再次提交同一安全信封。

默认安全会话 300 秒、时钟容差 120 秒。安全会话和防重放记录由数据库共享，所有进程必须设置相同的固定 `SECRET_KEY`；会话密钥加密存储，旧会话可跨进程和进程重启使用。旧记录仅在过期后清理。修改 `SECRET_KEY` 会使原会话失效。

设备安全接口统一错误响应 `{status:"error", msg, code}`：

| 状态 / code | 处理方式 |
| --- | --- |
| 401 `SECURITY_SESSION_INVALID` | 会话不存在、过期或存储密钥变化；设备可重新握手一次，生成新安全信封后重发 |
| 401 `SECURE_PROTOCOL_REQUIRED` | 未使用支持的安全协议；不降级、不自动重发 |
| 400 `SECURE_MESSAGE_REPLAY` | 消息 ID 或 nonce 已使用；不自动重发 |
| 400 `INVALID_SECURE_PAYLOAD` | 消息格式、MAC 或业务信封错误；不自动重发 |

网络超时及 5xx 不能证明业务未执行，设备不会自动重发。恢复重试最多一次，以免密钥配置不一致导致循环握手。无效响应 JSON 也视为失败，不能作为上传成功。

`GET /api/security/session/<id>` 查询安全会话是否有效。历史 ECC 上传默认关闭；仅在 `ALLOW_LEGACY_SECURE_UPLOAD=true` 时，通用 `/api/secure/upload` 才接受完全没有现代 header 的历史格式。此兼容模式不提供 v2 的认证与防重放保证，仅用于隔离迁移。人脸、心跳、状态同步始终不接受旧格式；带未知或损坏 header 的包也绝不降级。v2 后端默认启动无需加载旧 PEM 私钥。请求体上限为 8 MiB。

## 设备状态与日志

| 接口 | 权限 / 说明 |
| --- | --- |
| `POST /api/device/heartbeat` | v2 加密；业务 `{device_id, battery?, camera_status?, lock_status?, ip?}` |
| `POST /api/lock/sync` | v2 加密；业务 `{device_id}`，返回 `{target_status}` |
| `GET /api/lock/status?device_id=door_01` | JWT；目标状态和电量 |
| `GET /api/device/status?device_id=door_01` | JWT；可省略 ID 查询列表 |
| `GET /api/lock/history?page=1&per_page=10` | JWT；操作记录分页 |
| `GET /api/face/logs?page=1&per_page=10` | JWT；可按 passed、device_id 过滤 |
| `GET /api/alarms?status=pending&limit=10` | 历史公开告警查询 |
| `PATCH /api/alarms/<id>` | JWT；`{status:"resolved"}`，可选 pending/resolved/ignored |
| `POST /api/trigger_alarm` | 历史告警触发接口，会尝试发送配置的邮件 |
| `POST /api/secure/upload` | 安全信封；业务可含 Base64 `image` |
| `POST /api/snapshot/clear` | JWT；`{snapshot:"/static/captures/xxx.jpg"}`，省略清空实时帧 |
| `GET /video_feed` | 历史 MJPEG 预览接口 |

设备 `status` 是目标状态，`reported_status` 是设备最近一次上报的实际状态；心跳不会覆盖目标状态。两分钟内心跳视为在线。发送指令不会伪造新的心跳或上线状态。
