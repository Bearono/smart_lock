# Smart Lock

智能门锁软件，包含 Flask 后端、Vue 3 家居界面、树莓派摄像头网关和人脸识别工具。目标设备为 Raspberry Pi 4B / 2 GB，交付方式为 Docker。当前版本是待硬件验收的交付候选版，不能直接等同于已经完成工业现场验证的门锁产品。

## Docker 快速启动

新版采用温暖的家居界面与独立管理入口，设备默认使用 v3 AES-GCM 通信。具体实现、HTTPS 配置、工程结构、验收与实机边界见 [家门体验交付说明](docs/HOME_DELIVERY.md)。课程架构和威胁模型见 [设计说明](docs/COURSE_ARCHITECTURE.md)。

本版验收结果见 [家门体验与 v3 验收记录](docs/HOME_ACCEPTANCE.md)，算法对照见 [微基准记录](docs/HOME_BENCHMARK.md)。此前交付资料保留在 [完善方案](docs/DELIVERY_PLAN.md) 和 [历史验收记录](docs/DELIVERY_REPORT.md)。

在仓库根目录执行：

```sh
python deploy/init_secrets.py
docker compose build
docker compose up -d --wait
docker compose exec backend flask --app run create-admin --username operator
```

管理员密码通过交互输入，至少 12 字符，随后首次网页登录绑定 TOTP。没有默认账号和默认密码。打开 `http://localhost:8080`；入口默认仅监听回环地址，远程访问应经过 HTTPS 网关或受控隧道，不能把 HTTP 登录入口直接暴露公网。完整部署、设备登记、升级、备份和验收流程见 [部署手册](deploy/README.md)。

初始化服务显式创建/升级数据库，再启动非 root 后端工作进程。应用服务不在每次启动时执行数据库升级，也不会自动创建或提升管理员。数据库与图像保存在独立数据卷，密钥文件在 `deploy/secrets`，不进入镜像或版本库。不要运行 `docker compose down -v`，否则会删除数据卷。

## 设备与用户权限

```sh
docker compose exec backend flask --app run provision-device --device-id door_01 --service-url https://192.168.1.50:8443
docker compose exec backend flask --app run grant-device --username alice --device-id door_01
```

登记设备时交互输入至少 32 字节的独立随机口令，将同一口令配置到对应树莓派。用户先注册并由管理员批准，再由运维人员授予设备权限，最后在界面绑定设备。仅知道设备编号无法取得访问权。撤销权限使用 `grant-device ... --revoke`；更换设备口令重新执行登记命令，旧安全会话立即失效。

设备地址来自管理员登记，生产环境不采用设备自行上报的地址来派发请求。图像、设备状态和人脸日志按设备授权隔离；报警管理仅限管理员。旧的公开图像目录、明文帧上传和公开视频流已经关闭。前端携带认证头获取私有图像，不在图片 URL 中附带登录令牌。

## 开锁与确认

1. 密码验证只签发临时挑战，TOTP 成功后才签发登录 JWT。
2. 用户请求开锁，后端记录设备、nonce、有效期和认证策略，向登记设备发送签名挑战。
3. 树莓派采集并识别人脸，使用 SPAKE2 双向密钥确认 + v3 AES-256-GCM 加密上报；生产环境每次开门还要求 TOTP。
4. 确认认证后签发设备绑定的一次性令牌，消费令牌与创建开锁命令在同一事务内完成。
5. 命令只有 30 秒有效期；新命令取代旧待执行命令。设备同步响应有签名，并绑定原请求。过期或已撤权的命令不会继续下发。
6. 设备执行器应回传命令编号、结果及实际传感器状态，后端独立记录执行确认。消费令牌成功仅表示受理，绝不证明物理开锁完成。

用户与访客页面会查询命令结果；响应丢失时使用原凭证恢复原命令，避免重复消耗访客额度。撤权、解绑、账号驳回、认证锁定与口令轮换会永久撤销相关待执行命令。重新授权不会恢复这些旧命令。

设备安全会话加密持久化，防重放依靠数据库唯一约束，跨进程生效。设备仅在服务器明确返回会话失效时重新握手一次，不会因超时重发业务或降级旧协议。服务端对密码、注册、验证码和安全握手等敏感入口实施共享数据库限流。

**硬件边界：当前没有依据具体接线实现 GPIO 执行器，也没有活体检测算法。** 命令同步和回执协议已提供，但必须结合继电器、锁舌反馈及门磁型号实现并实测驱动后才能交付真实门禁。不会用模拟执行器或心跳冒充物理确认。图像相似度阈值不代表已测得的误识率。

## 开发与测试

后端和设备镜像均使用 Python 3.12：

```sh
cd BE_smart_lock/smart_lock
python -m venv .venv
# 激活环境后
pip install -r requirements.txt
pip install --no-deps ../../packages/smartlock_protocol
flask --app run init-db
flask --app run create-admin
python run.py
python -B -m unittest discover -s tests -p 'test_*.py' -v
```

开发模式临时随机密钥会使进程重启后会话失效；稳定联调也应设置固定的 `SECRET_KEY` 和 `JWT_SECRET_KEY`。显式启用 `SMART_LOCK_ALLOW_DEMO_DEVICES=true` 才允许隔离测试设备使用演示口令；生产模式禁止此选项。

前端使用 Node 24：

```sh
cd FE_smart_lock/smartlock
npm ci
npm run serve
npm test
npm run lint
npm run build
```

开发服务器将 `/api` 转发到本机 8000，Docker 使用同源代理。分离部署可设置 `VITE_API_BASE` 并在后端配置精确的 `CORS_ORIGINS`。

## 项目结构

| 目录 | 职责 |
| --- | --- |
| `BE_smart_lock/smart_lock/app` | 身份认证、授权、命令、设备通信和私有媒体 |
| `FE_smart_lock/smartlock/src` | 登录、控制台与访客界面 |
| `paspberry_pi` | 设备挑战签名校验、摄像头、人脸识别和通信客户端 |
| `deploy` | Docker 镜像、反向代理、备份恢复和验收手册 |
| `BE_smart_lock/smart_lock/tests` | 隔离回归测试与性能工具 |
| `wanganCV` | 历史独立实验工具，不属于生产部署 |

接口详见 [API 文档](API_DOCUMENTATION.md)。历史性能报表不是当前版本验收结果，不可作为容量或安全承诺。

设备软件的轮询、去重、恢复和驱动边界见 [设备执行说明](docs/DEVICE_EXECUTION.md)，当前验收证据见 [交付记录](docs/DELIVERY_REPORT.md)。
