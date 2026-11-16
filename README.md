# 安居 · SmartLock

[![CI](https://github.com/Bearono/smart_lock/actions/workflows/verify.yml/badge.svg?branch=main)](https://github.com/Bearono/smart_lock/actions/workflows/verify.yml)

基于树莓派的门禁验证系统。Web 和 Android 客户端共享业务后端，通过人脸与活体检测、动态验证码和一次性授权完成开门流程，独立 ARM64 服务模拟锁状态并返回执行回执。

**[下载 Android APK](https://github.com/Bearono/smart_lock/releases/download/v1.1.0/SmartLock-1.1.0.apk)** · [版本说明与校验文件](https://github.com/Bearono/smart_lock/releases/tag/v1.1.0) · [部署指南](deploy/README.md) · [文档目录](docs/README.md)

## 功能

- **身份验证**：账户审批、TOTP 登录、设备访问权限、人脸与活体验证。
- **门锁控制**：一次性开门授权、持久命令去重、执行回执和异常状态查询。
- **模拟锁面板**：独立展示锁舌状态与执行记录，支持全屏演示。
- **访客通行**：有效期、验证次数限制、凭证撤销和原命令结果恢复。
- **门前画面**：CSI 摄像头按需拍照、私有快照读取和访问控制。
- **管理与审计**：设备命名、成员权限、操作记录、人脸验证记录和告警处理。

## 安装客户端

APK 支持 Android 8.0 及以上。当前发布包为调试签名的本地联调版，默认服务地址为 `https://localhost:8443`，包含项目 CA 公钥证书。安装和证书说明见 [Android 指南](apps/android/README.md)。

**APK 需要连接已部署的后台服务。** 参考部署采用以下分工：

| 运行环境     | 服务                                          |
| ------------ | --------------------------------------------- |
| 电脑         | API、Web、HTTPS 入口、数据库和 ARM64 模拟门锁 |
| 树莓派       | CSI 采集、人脸与活体检测、设备心跳和命令执行  |
| Android 手机 | 客户端，通过 USB 端口转发访问电脑服务         |

USB 模式需要保持手机连接，并在电脑执行 `adb reverse tcp:8443 tcp:8443`。局域网或远程访问需要部署可达的 HTTPS 入口，并使用与该部署证书匹配的客户端。参考部署仅监听电脑回环地址。

## 启动后台

准备 Python 3.12 和 Docker Compose v2；Windows 使用 Docker Desktop 的 Linux 容器。按[开发指南](docs/development.md)安装 Python 依赖后，从仓库根目录执行：

```sh
python deploy/init_secrets.py
python deploy/init_local_tls.py
docker compose -f compose.yaml -f compose.tls.yaml up -d --build --wait backend web tls
docker compose exec backend flask --app run create-admin --username operator
```

浏览器访问 [https://localhost:8443](https://localhost:8443)。管理员密码由命令行交互设置，首次登录登记身份验证器。

完整运行还需按[部署指南](deploy/README.md)配置设备身份、树莓派、模型、模板和[模拟门锁](apps/lock_sim/README.md)。

## 仓库结构

| 路径                                                                 | 职责                                        |
| -------------------------------------------------------------------- | ------------------------------------------- |
| [apps/api](apps/api/README.md)                                       | Flask API、认证、授权、私有媒体、指令与审计 |
| [apps/web](apps/web/README.md)                                       | Vue 界面、业务状态与响应式交互              |
| [apps/android](apps/android/README.md)                               | Android 客户端、HTTPS 来源策略和 APK 构建   |
| [apps/device](apps/device/README.md)                                 | 树莓派相机、识别、心跳与执行器适配          |
| [apps/lock_sim](apps/lock_sim/README.md)                             | ARM64 模拟执行服务                          |
| [packages/smartlock_protocol](packages/smartlock_protocol/README.md) | 双端共享协议与密码实现                      |
| [deploy](deploy/README.md)                                           | 镜像、配置、维护、备份和发布工具            |
| [docs](docs/README.md)                                               | 架构、开发、接口、安全与验证说明            |

`workspace.toml` 声明组件与依赖入口，`manage.py` 提供统一检查和构建命令。

## 验证与维护

```sh
python manage.py check
python manage.py verify --output releases/verification
```

CI 覆盖仓库约束、API、Web、Android、容器和 amd64/arm64 设备镜像。真实设备验证与自动化检查的范围见[验证说明](docs/acceptance.md)。当前执行端为模拟门锁，所有执行结果保留 `SIMULATED` 标识。

APK 与校验文件通过 GitHub Releases 分发；源码、依赖锁定和工程文档由 Git 管理。运行密钥、数据库、个人照片和人脸模板不进入源码或安装包。

[贡献约定](CONTRIBUTING.md) · [安全问题反馈](SECURITY.md)
