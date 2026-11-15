# SmartLock

面向家庭的智能门锁与摄像头课程项目：Vue 3 网页、Flask 业务后端、Android 客户端、共享设备安全协议、Raspberry Pi 4B / 2GB 摄像头与人脸认证，包含音频传输和密码分发实验。实体锁与真实声学链路属于交付范围，尚待硬件验收。

软件具备安全认证、访客授权、私有画面、设备指令与失败回执闭环；当前硬件只有 Pi 和 OV5647，没有实体开门能力。人脸防伪模型已接入，独立真人和攻击效果验收尚待完成。不能将本项目称为已认证的工业门禁产品。

## 阅读入口

- [文档目录](docs/README.md)：当前资料和历史档案。
- [本轮安全与功能审查](docs/SECURITY_REVIEW_20261018.md)：修复、验证和未完成事项。
- [安全基线](docs/SECURITY_BASELINE.md)、[工程结构](docs/ENGINEERING.md)、[架构](docs/COURSE_ARCHITECTURE.md)。
- [部署与升级](deploy/README.md)、[接口文档](API_DOCUMENTATION.md)。
- [课程交付](docs/COURSE_FINAL_DELIVERY.md)、[人脸防伪与音频](docs/PAD_AUDIO_ACCEPTANCE.md)、[密码实验](docs/COURSE_CRYPTO_LAB.md)。

## 首次部署

需要 Docker Desktop（Linux 容器）。仓库根目录执行：

```sh
python deploy/init_secrets.py
python deploy/init_local_tls.py
docker compose -f compose.yaml -f compose.tls.yaml build
docker compose -f compose.yaml -f compose.tls.yaml up -d --wait
docker compose exec backend flask --app run create-admin --username operator
```

密码在交互窗口输入，无默认账户或默认密码。浏览器正式认证使用 https://localhost:8443，并先按部署手册信任自己生成的 CA；不要跳过证书警告。http://localhost:8080 是仅回环的开发预览入口，不应作为公开登录入口。

首次登录登记 TOTP。网页会话使用 HttpOnly Cookie、CSRF 校验和服务端退出撤销；不要复制 JWT 到浏览器存储。新密码使用 scrypt，生产设备使用 v3 双向密钥确认和 AES-GCM。私有快照和 MFA 凭据落盘加密，密钥与数据库需要分别备份和保护。

## 现有安装升级

此次包含数据迁移，**先停止写入并备份数据库、媒体与对应密钥**。同一密钥下执行 init-db 后再启动新后端和前端。旧明文凭据与媒体会认证加密；回滚须恢复旧数据和旧代码，不能只回滚镜像。完整流程见部署手册。

不运行 docker compose down -v。当前 Windows 容器保持 restart=no，Docker 和隧道由用户手动管理；Pi 用户服务自启是独立选项。

## 工程与验证

| 位置 | 职责 |
| --- | --- |
| apps/api/app | 认证、授权、设备控制、媒体与运维服务 |
| apps/web/src | 按业务域组织的网页和共享组件 |
| apps/android | Android 应用、JVM 测试与独立 SDK 构建入口 |
| packages/smartlock_protocol | 双端协议及隔离课程实验 |
| apps/device | 原生摄像头、人脸/PAD、设备工作线程与执行器接口 |
| deploy | 镜像、TLS、迁移、备份和验证工具 |
| docs | 当前资料；archive 保存历史证据 |
| examples/legacy_crypto | 禁止用于真实数据的历史加密示例 |
| examples/legacy_cv | 历史独立实验工具，不属于生产部署 |
| workspace.toml、manage.py | 组件清单与跨平台工作区入口 |
| .local | 保留的本机旧依赖和实验状态，Git 与镜像忽略 |

Python 3.12 后端按 requirements.txt 与 requirements.lock 安装，随后安装 packages/smartlock_protocol；前端使用 Node 24 与 npm ci。Pi 原生依赖使用 requirements.pi.txt，Picamera2/OpenCV 等来自匹配版本的系统包。设备镜像单独构建，不能用 x86 测试替代 ARM 实测。

```sh
python manage.py check
python manage.py verify --output releases/verification
python manage.py web-dev --port 5173
python deploy/audit_dependencies.py --output releases/dependency-audit.json
```

自动检查还需前端 test:browser、隔离后端 test:integration 和设备镜像 smoke/unittest；详见工程文档。源码包排除秘密、数据库、个人照片、模板、模型和本机依赖。main 按要求保留历史版本；历史 Git 中的秘密仍须视为已经暴露，不能重新使用。
