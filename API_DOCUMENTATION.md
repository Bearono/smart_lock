# SmartLock 接口契约

更新日期：2026-10-18。公开业务入口使用 HTTPS，同源反向代理到 Flask。除明确的公开接口和设备信封接口外，需要完成 MFA 的用户会话，且账户须 approved、登录版本有效、TOTP 仍激活。所有 JSON 请求必须为对象；默认请求上限 8 MiB。

## 浏览器与 API 认证

| 接口 | 请求与结果 |
| --- | --- |
| POST /api/register | username、password；注册 pending 账户，等待管理员批准 |
| POST /api/login/pre | username、password；返回 pre_token、totp_bound、role；首次登记额外返回 secret、qr_uri、qr_image |
| POST /api/login/mfa/bind | pre_token、code；完成首次登记和登录 |
| POST /api/login/mfa/verify | pre_token、code；已有认证器登录 |
| GET /api/account/session | 返回当前 username、role，不返回密码、TOTP 秘钥或登录令牌 |
| POST /api/logout | 撤销本次 JWT，并清除浏览器 Cookie |
| POST /api/account/password | current_password、new_password、code；成功后撤销旧登录和未完成访问能力 |

浏览器完成登录时设置 X-SmartLock-Session: browser。响应只含 username、role，访问令牌写入 HttpOnly Cookie smartlock_access；生产还要求 Secure、SameSite=Strict。写请求带 X-CSRF-TOKEN，值来自非 HttpOnly 的 smartlock_csrf Cookie。页面刷新通过 account/session 恢复身份；前端不存登录 JWT。

显式非浏览器 API 客户端不设置该会话头，完成 MFA 后仍获得 access_token，并使用 Authorization: Bearer。两种模式执行相同审批、撤销和设备权限检查。生产不能关闭 Cookie CSRF 或 Secure 保护。

密码至少 12 字符，最多 72 字节。pre_token 五分钟有效，最多五次校验尝试；TOTP 30 秒一步、前后一步容差，每个时间步跨接口只接受一次。已消费代码返回 401，等待下一组验证码后重试。重放同一登录挑战、账号撤权、过期等不会重新建立会话。

## 用户、设备授权和账户设置

| 接口 | 作用 |
| --- | --- |
| GET /api/admin/users | 管理员按 status 查询用户 |
| POST /api/admin/users/{id}/approve | 管理员批准；不会自动授予设备权限 |
| POST /api/admin/users/{id}/reject | 管理员驳回并撤销相关能力 |
| GET /api/admin/users/{id}/devices | 管理员读取已授权 device_ids |
| PUT /api/admin/users/{id}/devices/{device_id} | 管理员提交 granted 布尔值；撤销同步作废关联能力 |
| PUT /api/admin/devices/{device_id}/name | 管理员设置 1–60 字符 display_name |
| POST /api/mfa/admin/device/unlock | target_username；管理员解除该用户全部设备认证锁定，不授予新权限 |
| GET /api/mfa/status | 当前 TOTP 绑定与设备认证绑定列表 |
| POST /api/mfa/bind/device | device_id、可选 device_pubkey；需先有管理员授予的权限 |
| POST /api/mfa/unbind/device | device_id；撤销绑定及关联未完成授权 |
| POST /api/mfa/verify/totp | code、可选 credential_id；验证或激活认证器，成功会消费时间步 |
| POST /api/mfa/unbind/totp | code；要求新 TOTP，注销认证器并撤销登录与派生能力，当前网页无此入口 |

访问授权、设备认证绑定和设备自身的协议凭据是不同对象，不能互相代替。HTTP 接口与运维命令复用授权事务服务。

## 人脸与一次性开门授权

1. POST /api/mfa/open-door/request，用户提交 device_id。后端校验授权和锁定状态，创建五分钟认证会话，固定所需因子，再向登记的设备地址派发签名挑战。返回 request_id、nonce、requires_face、requires_totp、device_dispatch。
2. POST /api/mfa/open-door/face-result，只接受设备 v3 信封。解密内容如下：

```json
{"device_id":"door_01","request_id":"挑战编号","session_nonce":"挑战随机数","face_user_id":"用户名称","similarity_score":0.95,"liveness_score":0.91}
```

可选 snapshot_image 为 Base64 JPEG/PNG，必须由服务端验证和重编码。身份相似度至少 0.90；生产额外要求有限的 0–1 防伪分数达到 0.80。设备、nonce、有效期、账户与绑定同时校验。服务端不接受设备提供任意媒体 URL；防伪分数不构成摄像头可信证明，效果另行实测。

3. POST /api/mfa/open-door/confirm，用户提交 request_id 和所需 totp_code。成功一次性返回 unlock_token、device_id、expires_in:60。相同会话不能重复或并发签发。
4. POST /api/lock/unlock-token/verify，提交 unlock_token、device_id，原子消费令牌并创建指令。返回 command_id、command_accepted:true、hardware_confirmed:false；受理不等于实体开门。
5. POST /api/lock/command-status，持原 unlock_token、device_id 查询对应命令；不能执行控制或查询其他设备。已消费凭证仍能查询原结果，不能再次消费。

生产每次开门要求 TOTP；开发按固定会话策略验证。人脸日志通过 GET /api/face/logs 分页查询，受设备权限限制；返回 similarity_score、liveness_score、failure_reason 等字段，历史缺失值保持 null。

## 指令、状态和动态

| 接口 | 作用 |
| --- | --- |
| POST /api/lock/control | 用户提交 action:lock、device_id；直接解锁被拒绝 |
| GET /api/lock/commands/{id} | 有权限的用户查询原指令 |
| GET /api/lock/status | 设备状态，按授权过滤 |
| GET /api/lock/history | 分页操作审计，可按 device_id 查询 |
| GET /api/device/status | 按权限返回设备及状态，允许 device_id 筛选 |

命令通常 30 秒有效。pending 可以转为 executed、failed、expired、revoked 或 superseded，终态不得被冲突回执覆盖。设备锁反馈和 actuator_status 与命令状态独立；只有匹配的执行回执和反馈才确认执行。未知结果不得自动重发新命令。

状态中的 reported_status 来自设备反馈；目标 status 不是实际锁状态。is_online 由最近两分钟有效上报计算。actuator_status 为 AVAILABLE/UNAVAILABLE/ERROR/UNKNOWN；无执行器不能上报已完成真实上锁。缺失电量不填默认满电。时间携带显式时区时按偏移解释；历史无时区值不得猜测为 UTC。

## 私有画面与告警

| 接口 | 作用 |
| --- | --- |
| POST /api/video/capture | 用户提交 device_id，发送签名拍摄请求，只有确认本次新图片归属正确才成功 |
| GET /api/video/latest | device_id；读取已存快照，不触发拍摄，返回 snapshot、received_at、captured_at:null |
| GET /api/media/{filename} | 用户鉴权及设备授权后解密返回图片；Cookie 与 bearer 均支持 |
| POST /api/snapshot/clear | snapshot 或 snapshot_url；删除有权限的快照 |
| GET /api/alarms | 管理员按 status 查询报警 |
| PATCH /api/alarms/{id} | status:pending/resolved/ignored；管理员记录处理结果 |
| GET /api/admin/security/evidence | 管理员只读当前配置、记录数量和脱敏离线检查结果 |

历史公开 captures 路径、明文帧上传及公开视频流不开放。快照是单帧，不是实时视频；服务器接收时间不是采集真实性证明。报警邮件异步入队，email_status 是投递状态，不应将未配置 SMTP 解释成已送达。

## 访客

| 接口 | 作用 |
| --- | --- |
| POST /api/mfa/guest/create | device_id、可选 guest_name、valid_hours、max_uses；立即生效的有限期凭证 |
| GET /api/mfa/guest/list | 当前用户创建的凭证元数据，不重显完整凭证 |
| POST /api/mfa/guest/revoke/{id} | 撤销自己的凭证、未消费授权及相关待执行命令 |
| POST /api/mfa/guest/verify | 公开接口，pass_code；成功原子扣减验证额度并返回设备绑定授权 |

授权码只在创建时显示，数据库保存摘要。额度代表成功签发授权的验证次数，不是实体开门次数；响应丢失时恢复原命令，不自动重新验证扣减额度。

## 设备 v3 协议

POST /api/security/spake2/start 请求：

```json
{"version":"SL-SEC-v3","device_id":"door_01","client_pub":"Base64 SPAKE2_A 消息","client_nonce":"Base64 16 字节随机数","timestamp":1780000000,"request_id":"唯一请求编号"}
```

响应含 version、session_id、server_pub、server_nonce、expires_at、baseline_challenge、challenge。设备验证完整握手上下文，再 POST /api/security/spake2/confirm：version、session_id、proof。后端确认回执也有 proof；双方确认前不能发送业务。

业务信封：

```json
{"header":{"version":"SL-SEC-v3","session_id":"...","device_id":"door_01","request_id":"...","timestamp":1780000000,"nonce":"Base64 12 字节计数 nonce","endpoint":"/api/device/heartbeat","method":"POST","direction":"device-to-server"},"ciphertext":"Base64 AES-GCM 密文及标签"}
```

header 作为 AAD。session_key 派生专用方向密钥；nonce 在会话内单调递增，重启不复用旧客户端密钥。服务端验证时间、设备与上下文后，由持久唯一约束裁决 request_id 和 nonce 的重复。生产只允许 v3；v2 仅为隔离课程对照，不进行自动降级；旧固定 IV 上传格式已退休。

| 设备接口 | 解密业务内容 |
| --- | --- |
| POST /api/device/heartbeat | device_id、可选 battery/camera_status/lock_status/actuator_status/ip |
| POST /api/lock/sync | device_id；响应签名绑定原请求与端点，设备必须核验 |
| POST /api/lock/ack | device_id、command_id、status、reported_status、可选有界 failure_reason |
| POST /api/secure/upload | device_id、Base64 image；服务端重编码并加密存储 |
| POST /api/mfa/open-door/face-result | 上述会话绑定的人脸及防伪证据 |

设备服务 POST 要求 X-Command-Time、X-Command-Nonce、X-Command-Signature。HMAC-SHA256 的消息为紧凑 JSON 数组：method、path、时间字符串、nonce、原始请求体 SHA256；nonce 落盘去重，时钟容差 60 秒。签名不能替代 HTTPS。

## 运维与错误

GET /health/live 只表示进程存在；GET /health/ready 验证映射数据库结构。Pi 就绪还检查模型和模板，不能把 200 当作生物识别准确率或实体执行能力。

常见状态：400 参数或密文错误、401 认证/验证码错误、403 无权访问、409 并发/重放冲突、410 过期、423 认证锁定、429 限流、502 设备派发失败、503 就绪或静态密钥不可用。不要根据单个 HTTP 200 推断门已打开。

安全迁移、证书分发、备份和运行配置见 [部署手册](deploy/README.md)，完整限制见 [安全基线](docs/SECURITY_BASELINE.md)。
