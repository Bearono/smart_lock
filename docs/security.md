# 安全基线

更新日期：2026-10-18。本基线对照 OWASP 与 IETF 文档，用于可检查的工程约束；不代表 ASVS 认证、FIPS 认证或第三方渗透测试通过。

## 身份与浏览器会话

- 新密码使用 Werkzeug scrypt，参数 N=131072、r=8、p=1，16 字符随机盐。现有 bcrypt 记录在正确密码认证的事务中平滑升级。用户密码是单向哈希，不作可逆加密；保留 12 字符与 72 字节边界以兼容现有账户策略。
- scrypt 单次约需 128 MiB 内存。每个 worker 同时只运行一次内存型密码操作，配合默认两个 worker 和 512 MiB 容器预算，避免多线程认证并发耗尽内存；扩容 worker 时必须重新评估内存与限流。
- 密码正确只能取得五分钟登录挑战。TOTP 登记或验证成功后才得到登录会话。挑战有次数限制，账号审批、auth_version 与有效认证器在每次鉴权时重新检查。
- 浏览器发送 X-SmartLock-Session: browser，得到 HttpOnly 会话 Cookie；响应不返回可供浏览器持久化的 access_token。生产 Cookie 设置 Secure、SameSite=Strict，令牌路径限定 /api；页面仅在内存保存用户名和角色。
- 不在 localStorage、sessionStorage 或 URL 保存登录令牌。旧版浏览器存储在新前端加载时清除；这不等于从历史浏览器备份抹除数据。
- Cookie 写请求必须提供双提交 CSRF 头 X-CSRF-TOKEN，与 smartlock_csrf Cookie 匹配。只读会话接口供页面刷新恢复身份；角色显示不代替服务端授权。
- 退出登录将 JWT jti 写入持久撤销表并清除 Cookie，重启后仍拒绝该令牌。网络失败时界面不得虚报已经退出。显式 API 客户端仍可使用 bearer 登录；不应将其令牌放回网页存储。
- TOTP 采用 30 秒步长、前后一步容差。通过数据库条件更新，每个认证器的时间步只能成功消费一次，并在登录、开门及密码操作之间共享。刚登录后再次验证，应等待新验证码；密码变更和旧请求不能复用已消费代码。

## 传输和设备协议

- 对外入口使用经客户端验证的 HTTPS。TLS 只启用 1.2/1.3；1.2 限制为 ECDHE 与 AEAD 套件，不接受匿名、静态 RSA 密钥交换或 CBC 套件。测试使用的回环 HTTP 不是公开部署方案。
- 生产设备地址必须 HTTPS，回环软件夹具是明确例外。Pi 生产通信始终要求 HTTPS 并校验 CA；不使用 verify=False 或跳过 SSH 主机密钥验证。
- 生产启动拒绝 v2 和旧式 ECC/CBC 上传开关。历史不带认证的固定 IV 加密示例已移出运行目录，旧上传解密器永久拒绝该格式。
- v3 使用 SPAKE2、HKDF-SHA256、双向确认和 AES-256-GCM。独立方向密钥、96 位计数 nonce、会话消息上限；进程重启重新握手，不恢复旧客户端密钥并重置计数。
- AAD 绑定设备、会话、方向、方法、端点、请求 ID 和时间；数据库唯一约束阻止跨 worker 和重启重放。通过鉴别后才消费重放凭据，业务失败也不释放有效信封。
- 后端设备指令使用独立用途 HMAC-SHA256，覆盖原始请求体摘要、路径、方法、时间和 nonce；签名本身不提供保密性，仍须 TLS。同步响应绑定原请求，控制受理与实际执行回执分开。
- SPAKE2 Python 库不是常数时间实现；本项目附加的信封与握手扩展是应用协议，并非通过独立密码协议审计。不能宣称仅因使用 RFC 中算法就取得工业认证。

## 静态数据与密钥

- MFA 凭据由随机化 Fernet 认证加密后落库，领域代码读取时解密；与设备会话存储使用不同用途派生。生产读取未迁移明文直接失败。
- 私有快照使用 AES-256-GCM 落盘，独立用途密钥、随机 96 位 nonce，AAD 绑定文件名及设备。鉴权通过后才解密发送；错密钥、错设备、换文件名和密文篡改均拒绝。
- SECRET_KEY 与 JWT_SECRET_KEY 必须独立、持久、至少 32 字节且由安全随机数产生。它们不是人类密码；长度检查不能证明熵。密钥文件不进 Git、镜像和公开交付包。
- 当前静态加密密钥从应用主密钥按用途派生，不是 HSM/KMS。应用主密钥与完整数据卷同时泄露时，此加密不能继续保护数据。轮换主密钥须先维护窗口备份，再通过旧密钥解密和新密钥重加密；直接替换会造成不可读，禁止以失败后回退明文处理。
- Pi 人脸模板与源照片仍依赖设备文件权限与主机存储保护，未实现 TPM、可信执行环境或模板专用磁盘加密。源码不分发个人样本；端点管理员仍处于信任边界内。
- 邮件使用 SMTP_SSL，并显式传入 ssl.create_default_context() 验证证书及主机名；队列中成功标记与真实外部送达需分别验收。

## 升级与回滚

停写并备份旧数据库和媒体、另存密钥后，在同一密钥下运行 init-db。升级新增 OTP 消费计数与退出撤销表，将历史凭据及登记媒体原地认证加密；媒体逐文件原子替换，重复执行不重复加密。备份本身仍可能包含旧明文，应按敏感资料管理。

升级后的密文不能交给旧版代码直接读取。回滚必须同步恢复升级前的数据备份和匹配的旧代码、旧密钥，不能只回滚镜像。MySQL 分支包含字段扩容 SQL，但本次迁移回归在 SQLite 上执行，未作 MySQL 实机验收。

## 依据

- [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)：现代密码哈希与 scrypt 参数。
- [OWASP Cryptographic Storage](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html)：认证加密、随机数和密钥生命周期。
- [OWASP HTML5 Security](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html)：不在 Web Storage 保存会话标识。
- [OWASP TLS](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html)：传输版本、套件与证书验证。
- [RFC 6238 §5.2](https://www.rfc-editor.org/rfc/rfc6238.html#section-5.2)：成功验证后不能再次接受同一 OTP。
- [RFC 9382](https://www.rfc-editor.org/rfc/rfc9382.html)：SPAKE2 算法；不是对本项目自定义协议的认证。
