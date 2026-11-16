# 部署与维护

参考部署由电脑上的 API、网页、HTTPS 和 ARM64 模拟锁，以及树莓派上的 CSI 摄像头服务组成。首次部署先阅读[开发环境](../docs/development.md)；支持范围见[验证说明](../docs/acceptance.md)。所有命令从仓库根目录执行。

## 电脑服务

```sh
python deploy/init_secrets.py
python deploy/init_local_tls.py
docker compose -f compose.yaml -f compose.tls.yaml up -d --build --wait backend web tls
docker compose exec backend flask --app run create-admin --username operator
```

初始化工具只创建缺失密钥，不覆盖已有文件。管理员密码交互输入；首次登录需要绑定身份验证器。浏览器访问 [https://localhost:8443](https://localhost:8443)；HTTP 8080 仅供本机预览。

本地 CA 位于 `deploy/tls/ca.crt`，必须核对后由使用者决定是否信任，不能关闭证书验证。

已有部署可直接启动现有容器；Windows 上需先启动 Docker Desktop：

```powershell
docker start smart-lock-backend-1 smart-lock-web-1 smart-lock-tls-1
```

上述容器名称对应仓库默认项目名 `smart-lock`。`docker start` 仅启动指定容器，保留原有数据卷；Compose 的 `start` 可能同时启动依赖的 `init` 服务。首次安装、配置变更和升级使用 Compose；停止使用 `docker compose -f compose.yaml -f compose.tls.yaml stop`。通知发送作为独立服务配置和启动。

API 不单独暴露宿主机端口；入口只绑定回环地址。后端以非 root 身份运行，文件系统只读，业务数据保存在 `data` 卷。`/health/live` 检查进程，`/health/ready` 检查数据库结构；设备在线情况以有效心跳为准。

## 账户与设备

注册账户需要管理员审批，并单独授予设备权限：

```sh
docker compose exec backend flask --app run provision-device --device-id door_01 --service-url https://DEVICE_ADDRESS:8443
docker compose exec backend flask --app run grant-device --username alice --device-id door_01
```

设备口令至少 32 字节，应独立随机生成。设备端通过 `SMART_LOCK_DEVICE_PASSWORD_FILE` 读取同一口令。服务地址和证书 SAN 必须一致；设备只接受带签名的后端指令。设备权限、用户认证绑定与设备协议凭据分别管理。

授权撤销使用 `grant-device --revoke`；账户恢复使用 `recover-account`，密码始终交互输入。密钥轮换、撤权和密码变更会作废相关会话与授权，具体规则见[安全基线](../docs/security.md)。

## 树莓派 CSI 服务

原生服务使用系统 Picamera2、OpenCV 和 NumPy，不将通用 pip 包安装进系统 Python：

```sh
sudo python3 deploy/pi_dependencies.py --linger-user SERVICE_USER
python3 deploy/pi_native.py prepare
python3 deploy/pi_native.py check-runtime
```

准备 `deploy/.env`，限制为服务账户可读，并显式配置：

| 配置                              | 内容                      |
| --------------------------------- | ------------------------- |
| `SMART_LOCK_ENV`                  | `production`              |
| `SMART_LOCK_DEVICE_ID`            | 已登记设备 ID             |
| `BACKEND_URL`                     | 验证证书的 HTTPS 后端地址 |
| `SMART_LOCK_CA_BUNDLE`            | CA 公钥文件               |
| `SMART_LOCK_DEVICE_PASSWORD_FILE` | 独立设备口令文件          |
| `DEVICE_STATE_DIR`                | 可写的命令去重目录        |
| `SMART_LOCK_MODELS_DIR`           | 已校验模型目录            |
| `SMART_LOCK_TEMPLATES_DIR`        | 已登记人脸模板目录        |
| `SMART_LOCK_CAMERA_BACKEND`       | `picamera2`               |

为服务提供 `deploy/tls/pi-native.crt`、`pi-native.key` 和 CA 公钥，证书 SAN 必须覆盖后端实际访问的地址。设备不保存 CA 私钥。现有证书升级可用 `repair_local_tls.py` 检查并生成独立修复副本；该工具不会直接覆盖在线证书。

```sh
python3 deploy/pi_native.py install-service
systemctl --user status smart-lock-device
journalctl --user -u smart-lock-device --no-pager -n 50
```

原生服务监听 `127.0.0.1:5443`，单 worker、双线程，串行使用相机和模型；退出时释放相机。参考拓扑中，电脑与 Pi 通过 SSH 转发连接：

```sh
python deploy/pi_tunnel.py --host PI_ADDRESS --user SERVICE_USER --identity PATH_TO_PRIVATE_KEY
```

电脑 `15443 → Pi 5443`，Pi `18443 → 电脑 8443`。Pi 后端地址为 `https://localhost:18443`，Docker Desktop 后端登记设备地址为 `https://host.docker.internal:15443`。证书需包含这些主机名。保持转发进程运行；关闭后通信中断，恢复需重新启动，不创建电脑自动重连任务。

模拟锁通过独立签名请求和 HTTPS 连接，配置及 Pi 端执行器变量见 [ARM64 模拟门锁](../apps/lock_sim/README.md)。手机安装和 USB 转发见 [Android 指南](../apps/android/README.md)。

## 模型与人脸模板

检测模型使用固定来源与摘要校验；运行服务不自动下载模型：

```sh
python deploy/prepare_face_models.py --download
python deploy/prepare_face_models.py
```

生产人脸验证还要求 MiniFASNetV2 ONNX。在工作站独立导出环境安装 PyTorch CPU 2.9.0、onnx 1.19.1、NumPy 2.2.4、opencv-python-headless 4.11.0.86，执行：

```sh
python deploy/export_pad.py --cache releases/pad-upstream --output deploy/device/models
```

将模型、`MINIFASNET-LICENSE` 和 `pad-export.json` 一起交付设备。来源、摘要及导出过程由脚本校验；模型缺失或被修改时就绪检查失败。Pi 不需要安装 PyTorch。

核实账户身份与授权后，在具备视觉依赖的维护环境中处理 3–20 张不同的本人图像：

```sh
python apps/device/manage_templates.py --directory deploy/device/templates enroll --username alice --images capture1.jpg capture2.jpg capture3.jpg
python apps/device/manage_templates.py --directory deploy/device/templates validate
python apps/device/manage_templates.py --directory deploy/device/templates list
python apps/device/manage_templates.py --directory deploy/device/templates remove --username alice
```

每张图像只能有一张脸。模板须为 128 维有限非零向量，禁止 pickle；替换需显式 `--replace`。更新后重启设备或调用受签名保护的模板刷新接口。删除人脸模板不能代替后端撤权。缺少模板时保持就绪失败，不安装虚构数据。

## 设备容器

`compose.device.yaml` 提供 USB/V4L2 部署选项；CSI 使用上面的原生服务。镜像在内存充足的目标架构主机构建，避免在 2 GB Pi 上承担 C++ 构建负载。

```sh
docker build -f deploy/device.Dockerfile -t smart-lock-device:local .
docker run --rm --network none --read-only --tmpfs /tmp smart-lock-device:local python /app/device_smoke.py
docker run --rm --network none --read-only --tmpfs /tmp smart-lock-device:local python -B -m unittest discover -s /app/tests -v
```

部署前提供 `deploy/secrets/device_key`、模型和模板，设置 `SMART_LOCK_DEVICE_ID`、`BACKEND_URL`、`DEVICE_TLS_BIND_IP` 及摄像头 `VIDEO_GID`。维护主机执行 `issue_device_tls.py --host DEVICE_ADDRESS` 签发独立设备证书，仅传输 `device.crt`、`device.key` 和 `ca.crt`：

```sh
docker compose -f compose.device.yaml -f compose.device.tls.yaml up -d --wait
```

## 升级、备份与恢复

升级前记录提交和镜像，停止所有数据写入者，并成套保存数据卷与应用密钥。备份工具校验 SQLite 和文件摘要；备份本身不加密，应置于受控或加密存储。

```sh
docker compose stop web backend notifications
docker compose run --rm --no-deps -v "$PWD/deploy/backups:/backups" init python /app/backup.py backup /backups/release.zip
```

先创建 `deploy/backups`，在 Linux 上确保容器 UID 10001 可写。归档必须使用新文件名。恢复只允许写入新的空目录或空卷，先独立验证再切换：

```sh
docker compose run --rm --no-deps -v "$PWD/deploy/backups:/backups" init python /app/backup.py restore /backups/release.zip --data /backups/restore-check
```

新镜像构建后显式运行初始化迁移，再启动业务服务。不能只回滚代码而继续读取不兼容的新数据库或密文；回滚需要匹配的数据和密钥。不要删除在线数据卷来解决升级问题。

验收、依赖安装和源码发布统一使用[开发指南](../docs/development.md)中的命令。硬件测试与软件夹具分开记录，模拟执行不代表实体锁动作。
