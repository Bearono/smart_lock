# 部署、维护与验收

## 交付边界

本版本交付软件与 Docker 配置，默认单站点、小规模 SQLite 部署。Pi 4B 2 GB 优先仅运行设备容器；后端可在另一台 Docker 主机部署。如果共机运行，必须实测内存、推理延时、并发和温度后再确定容量。没有以 Windows 或 x86 容器的运行结果推断 ARM 硬件性能。

上线前必须完成 GPIO/锁舌反馈/门磁驱动、断电保护、紧急出口、活体与误识率测试、现场网络/TLS、长期稳定性和备份恢复验收。此处是尚待验收的明确边界，不是已经具备的能力。

## 初始化与启动

```sh
python deploy/init_secrets.py
docker compose build
docker compose up -d --wait
docker compose exec backend flask --app run create-admin --username operator
```

脚本仅生成缺失密钥，不覆盖现有密钥。Linux 主机密钥目录权限为 0700，文件为 0444，以便容器内非 root UID 读取挂载文件；其他主机账号无法遍历目录。Windows 下请由运行 Docker 的账号执行生成脚本；若通过隔离账号生成，必须仅向运行 Docker 的账号授予该目录及文件读取权限，不能授予 Everyone。

`init` 服务成功完成后后端才启动，健康检查通过后入口服务启动。后端文件系统只读，只有 `/data` 和临时目录可写。不要同时运行多个初始化作业。数据库迁移前先停止写入并备份；当前兼容升级不是通用的可逆迁移系统，回滚依赖备份。

入口绑定 `127.0.0.1:8080`，数据库没有公开端口。生产远程访问必须在入口前配置 HTTPS。`TRUST_PROXY=true` 只允许后端位于受控代理之后；不要单独发布后端端口。代理覆盖转发地址头，应用只信任一跳。CORS 默认不开放跨源，可用明确的 `CORS_ORIGINS` 白名单配置分离前端。

`/health/live` 反映进程存活；`/health/ready` 检查所有映射表及字段可查询；不代表设备在线、摄像头可用或锁具安全。日志默认输出到容器日志，限制每文件 10 MB、保留 3 份。

## 用户与设备登记

1. 创建管理员，首次登录进行 TOTP 绑定。
2. 用户注册（密码至少 12 字符、最多 72 字节），管理员审批。
3. 为每台设备登记独立随机口令和固定服务地址：

```sh
docker compose exec backend flask --app run provision-device --device-id door_01 --service-url https://192.168.1.50:8443
docker compose exec backend flask --app run grant-device --username alice --device-id door_01
```

输入的设备口令至少 32 字节，应来自密码管理器或随机生成器。不要使用示例词串或与登录密钥共用。用户完成授权后，在前端绑定对应设备。撤销使用相同 `grant-device` 命令附加 `--revoke`。口令轮换会作废设备旧会话、未用令牌、认证会话和待执行命令，设备须配置新口令才能重新握手。

`SECRET_KEY` 同时保护设备会话和登记口令。轮换它会使已有登记口令无法解密，必须重新登记全部设备；只轮换 JWT 密钥则要求用户重新登录。数据卷备份与两份应用密钥必须成套恢复，并分别安全保管。

## Raspberry Pi 4B / 2 GB

使用 64 位系统和 Docker。`compose.device.yaml` 默认对接 `/dev/video0` 的 USB/V4L2 摄像头，不能据此声称 CSI/Picamera2 已通过容器验证。CSI 摄像头需要针对系统 libcamera、设备节点和权限单独验证。

1. 把登记口令保存为 `deploy/secrets/device_key`，只允许运维账号读取其父目录。
2. 在维护主机执行 `python deploy/prepare_face_models.py --download`，把固定版本的模型放入 `deploy/device/models`。再次执行不带 `--download` 的命令校验模型。来源和 SHA-256 固定在 `model_manifest.py`；缺失或被改动的模型不通过设备就绪检查，生产进程不自动下载。
3. 使用下方模板管理工具登记已批准账户，输出到 `deploy/device/templates`。模板用户名与后端账号一致，目录以只读方式挂载。
4. 按 [家门交付说明](../docs/HOME_DELIVERY.md) 配置后端与设备 HTTPS：只传输设备服务证书、设备服务私钥和 CA 公钥，CA 私钥留在维护主机。设备服务证书 SAN 必须匹配后端登记地址。
5. 设置变量并部署：

```sh
export SMART_LOCK_DEVICE_ID=door_01
export BACKEND_URL=https://your-backend.example
export DEVICE_TLS_BIND_IP=192.168.1.50
export VIDEO_GID=$(getent group video | cut -d: -f3)
docker compose -f compose.device.yaml build
docker compose -f compose.device.yaml -f compose.device.tls.yaml up -d --wait
```

上面的镜像构建应在内存充足的 ARM64 构建主机执行，Pi 4B / 2 GB 不直接承担双任务 C++ 编译。可在构建主机执行 `docker save smart-lock-device:local -o smart-lock-device-arm64.tar`，传到 Pi 后执行 `docker load -i smart-lock-device-arm64.tar`，再只执行 `up -d --wait`。AMD64 主机可用 `docker buildx build --platform linux/arm64 --load -f deploy/device.Dockerfile -t smart-lock-device:local .`，跨架构编译较慢。GitHub CI 已在原生 ARM64 runner 验证该 Dockerfile，不把 runner 的内存或耗时当作 Pi 实测。

服务地址应限于受控局域网/VPN，防火墙仅允许后端访问。每次 POST 必须有后端签名；修改模板建议在维护窗口更新只读挂载后重启。设备只用一个工作进程、两个请求线程，并在工作进程启动后运行独立的心跳和命令轮询线程；摄像头采集串行进行，避免重复装载人脸模型。内存上限 1200 MB 是保护配置，不是已经验证的峰值。

设备镜像统一使用 Python 3.12，固定 NumPy、无界面 OpenCV 与 Pillow 版本；dlib 19.24.6 在独立构建阶段编译为 wheel，运行镜像不携带编译工具。构建阶段将并行任务限制为 2，建议在构建主机生成镜像后分发到设备。不要将本机 x86 构建结果视为 ARM 验收：ARM 镜像必须在对应架构单独构建验证，摄像头采集与推理性能仍需 Pi 实机测试。Docker 文件不包含 GPIO 驱动，不默认授予 privileged 权限。

## 备份与恢复

备份必须先停止所有写入者（包括设备向后端上传）。工具包含 SQLite 完整性检查、每文件 SHA-256 校验，采用流式处理以控制内存。归档本身不加密，应放在受控目录或加密备份系统；应用密钥单独备份。

```sh
mkdir -p deploy/backups
docker compose stop web backend notifications
docker compose run --rm --no-deps -v "$PWD/deploy/backups:/backups" init python /app/backup.py backup /backups/release.zip
docker compose up -d --wait
```

Linux 上归档目录应对容器 UID 10001 可写。备份文件名必须是新名字，已有归档不会覆盖。设备本地指令防重放数据卷也需要保护；重建或删除它会丢失本地接收记录。

恢复演练请使用新建空目录/卷，不能直接覆盖在线数据：

```sh
mkdir -p deploy/backups/restore-check
docker compose run --rm --no-deps -v "$PWD/deploy/backups:/backups" init python /app/backup.py restore /backups/release.zip --data /backups/restore-check
```

恢复后先用独立实例验证管理员登录、设备授权、图像可读及过期指令不会执行，再安排正式切换。回滚应用版本时同时恢复匹配的数据卷；不可假定新版数据库自动向下兼容。

## 升级与验证

固定应用提交和镜像 digest，保存依赖锁文件及测试报告；升级前备份，再重建镜像、执行初始化服务并启动。不要直接在正在运行的容器里安装依赖。

```sh
python -B -m unittest discover -s BE_smart_lock/smart_lock/tests -p 'test_*.py' -v
cd FE_smart_lock/smartlock
npm ci
npm test
npm run lint
npm run typecheck
npm run format:check
npm run build
```

现场验收至少覆盖：

| 验收项目 | 必须证明的行为 |
| --- | --- |
| 权限隔离 | 未授权账号无法绑定、查询设备或读取图像；撤权后不能继续开锁 |
| 断网与恢复 | 旧开锁命令超时后不再下发；网络超时不导致重复动作 |
| 设备重启 | 已接收指令不重复执行；不确定执行结果不能报告成功 |
| 机械与电气 | 接线、继电器极性、驱动电流、锁舌反馈、门磁及断电状态经实测 |
| 身份验证 | 照片/视频攻击、光照变化、误拒和误识率达到项目要求 |
| 持续运行 | Pi CPU、内存、温度、存储增长、离线恢复和时间同步稳定 |
| 故障恢复 | 在另一空实例恢复数据库、图像与密钥，实际验证业务 |

## 软件验收与打包

安装后端锁定依赖、共享协议包（`pip install --no-deps ./packages/smartlock_protocol`）和前端 `npm ci` 后，从仓库根目录执行：

```sh
python -B deploy/verify.py
python deploy/package_release.py releases/smart-lock-software.zip
```

统一验收会运行后端全量测试、真实本机 HTTP 软件联调、前端测试、ESLint 和生产构建，任一步失败即停止。结果、日志和被验证源码的 SHA-256 写入 `releases/verification`。发布脚本只接受与通过验证源码一致的工作区，打包后逐文件回读校验，同时生成 ZIP 的 `.sha256` 文件。

源码包包含应用、部署文件、测试、文档与验收证据；不包含数据库、密钥、个人模板、CV 模型、node_modules/虚拟环境和构建产物。部署时安装锁定依赖，并按设备部署章节提供模型及设备配置。解压后可使用同一 `verify.py` 重新验收，不能把已有报告当作目标环境运行结果。

## 账号与授权运维

管理员可在网页 Admin → Device access 中管理已登记设备的用户权限。设备口令登记仍通过运维命令完成，密钥不进入网页列表。用户可在 Account 中提交当前密码、新密码和认证器验证码修改密码，成功后重新登录。

忘记密码或丢失认证器时，由具备主机运维权限的人核实身份后执行：

```sh
docker compose exec backend flask --app run recover-account --username alice
# 仅在认证器丢失时使用；之后首次登录必须绑定新认证器
docker compose exec backend flask --app run recover-account --username alice --reset-totp
```

密码通过交互输入，不写在命令行。恢复会使旧登录、认证挑战和待执行授权失效并记录审计；不改变角色、审批状态或设备授权名单，不自动提升权限。

## 告警与存储维护

报警与邮件任务在同一个数据库事务中保存，`notifications` 服务独立派送邮件。未配置 SMTP 时任务状态为 `disabled`，不会尝试联网；配置后新任务最多重试 5 次，退避等待，工作租约 120 秒，SMTP 单次连接超时 10 秒。崩溃发生在邮件发出后、状态提交前时可能重复投递，不能声称邮件严格只发送一次。邮件失败不会删除报警记录。

需要邮件通知时，通过部署覆盖文件为 backend 与 notifications 同时配置 `SMTP_SERVER`、`SMTP_PORT`、`SENDER_EMAIL`、`RECEIVER_EMAIL`，并挂载独立凭据文件，通过 `SENDER_PASSWORD_FILE` 指向它。配置变更后重建这两个容器。既有 disabled 任务不会自动补发；先在受控测试收件箱验收，不将邮件作为唯一告警渠道。

```sh
# 预览超过 30 天的媒体，默认最多 1000 项，不删除
 docker compose exec backend flask --app run prune-media --older-than-days 30
# 确认保留策略并完成备份后执行；历史日志保留，但对应图像不再可读
 docker compose exec backend flask --app run prune-media --older-than-days 30 --apply
# 单次处理邮件队列，日常由 notifications 服务持续运行
 docker compose exec backend flask --app run deliver-alarms --limit 20
```

媒体保留策略由运维显式执行，容量阈值及磁盘告警仍需主机监控。备份前必须停止 notifications，因为它也是数据库写入者。恢复在同目录旁的暂存目录完成文件校验和 SQLite 检查，通过后才替换空目标目录；校验失败不会向目标发布半份数据。

`schema.py` 集中管理兼容字段升级，`init-db` 仍需在停写、备份后单独执行。此次升级增加 `users.auth_version`、`door_commands.guest_pass_id`、`unlock_tokens.command_id` 和 `alarm_deliveries` 表，回滚应恢复配套备份。

设备心跳每 30 秒采集一次摄像头健康状态；当前没有安装 GPIO 反馈驱动，因此锁状态始终上报 UNKNOWN，绝不会从命令目标推断实际开锁。设备进程存活检查不代表摄像头或锁具可用。

当前不宣称具备 HA、多租户隔离、审计防篡改或合规认证。

部署顺序依据 [Docker Compose 官方说明](https://docs.docker.com/compose/how-tos/startup-order/)；Flask 使用独立生产 WSGI 服务，参见 [Flask 部署文档](https://flask.palletsprojects.com/en/stable/deploying/)。Vue 迁移依据 [官方迁移说明](https://router.vuejs.org/guide/migration/)。

设备命令执行、持久化状态卷和驱动接入契约见 [设备软件执行说明](../docs/DEVICE_EXECUTION.md)。默认没有实物驱动时报告执行失败；命令接收和回执重试已由软件执行器负责。

本机 8080 被占用时可设置 `SMART_LOCK_WEB_PORT=18080` 再启动；监听地址仍为 127.0.0.1。使用 `docker compose -p smart-lock-acceptance` 可为验收隔离网络和数据卷。不要把验收账号用于实际部署。

设备镜像可单独执行无硬件验收：

```sh
docker build -f deploy/device.Dockerfile -t smart-lock-device:local .
docker run --rm --network none --read-only --tmpfs /tmp smart-lock-device:local python /app/device_smoke.py
```

该检查加载视觉依赖、处理合成空白图像，并验证设备 HTTP 健康与签名拒绝边界。它不启动摄像头，不连接后端，也不执行锁具动作。持续集成中的 `device-image` 作业执行相同检查。

## 人脸模板登记、替换与删除

这是受控运维流程，不是网页自助登记。先核实被登记者身份及后端账户审批、设备授权；在具备设备镜像视觉依赖的维护环境中处理 3–20 张不同的本人图像。每张只允许一张人脸，重复图片、无脸/多脸和损坏图片均拒绝。图像质量、是否同一人仍由登记者核查，不宣称自动活体校验。

```sh
python paspberry_pi/manage_templates.py --directory deploy/device/templates enroll --username alice --images capture1.jpg capture2.jpg capture3.jpg
python paspberry_pi/manage_templates.py --directory deploy/device/templates validate
python paspberry_pi/manage_templates.py --directory deploy/device/templates list
# 替换必须显式指定 --replace；不会默认覆盖已有登记
python paspberry_pi/manage_templates.py --directory deploy/device/templates install --username alice --vector approved-vector.npy --replace
python paspberry_pi/manage_templates.py --directory deploy/device/templates remove --username alice
```

工具与推理共用 `SMART_LOCK_TEMPLATES_DIR`、`SMART_LOCK_MODELS_DIR`；默认路径分别是设备的 `cv/data/templates/templates` 和 `cv/models`。向量要求 128 维、有限非零数值，读取禁止 pickle，安装原子发布并拒绝符号链接。移除只删除指定账户模板。更新后验证并在维护窗口重启设备，使推理缓存刷新：`docker compose -f compose.device.yaml -f compose.device.tls.yaml restart device`。删除模板不能代替后端撤销设备授权，两者应一起执行。

设备 `/` 仅表示进程存活；`/health/ready` 校验固定模型和至少一个合法模板。就绪不表示摄像头、锁具、识别准确率或活体能力通过验收。模型下载来源：[OpenCV 4.11.0 检测配置](https://github.com/opencv/opencv/blob/4.11.0/samples/dnn/face_detector/deploy.prototxt) 和 [OpenCV 检测模型](https://github.com/opencv/opencv_3rdparty/tree/dnn_samples_face_detector_20170830)。本地模型与个人模板不进入 Git 或源码交付包。

初次 TOTP 登记窗口为 5 分钟；超时重新登录取得新登记信息。重复预登录复用当前窗口，不能通过旧登记替换已激活的认证器。历史重复待绑定凭据在成功激活时作废。

连续认证失败达到锁定阈值时自动保存 `AUTH_LOCKOUT` 告警及通知任务，同一次锁定只生成一次；管理员解除锁定后再次触发可产生新告警。SMTP 未配置时通知明确为 disabled，后台告警仍可查看和处理。

设备离线验收包含模板与就绪接口回归：

```sh
docker run --rm --network none --read-only --tmpfs /tmp smart-lock-device:local python -B -m unittest discover -s /app/tests -v
```

最新复核范围、证据和剩余能力见 [软件验收复核](../docs/SOFTWARE_ACCEPTANCE_20261009.md)。
