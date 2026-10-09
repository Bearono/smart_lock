# 家门体验与 v3 协议软件验收

验收日期：2026-10-09。验证主机为 Windows / AMD64，目标硬件为 Raspberry Pi 4B / 2 GB。此记录区分本机软件、容器架构和真实硬件，不把隔离测试设备当作已安装的门锁。

## 已通过的软件检查

| 范围 | 结果与证据 |
|---|---|
| Python 回归 | 101 个用例通过；覆盖权限、MFA、访客额度、命令生命周期、私有媒体、持久重放、v3 上下文与确认、证书身份、串行推理所有权 |
| 前端行为 | 12 个流程用例通过；包括原凭证恢复、取消与迟到结果、执行成功必须有硬件确认 |
| 工程检查 | ESLint、Vue/TypeScript 类型检查、Prettier 和生产构建通过 |
| 浏览器行为 | 登录、撤权、跨路由命令恢复、私有图片代次、访客公共页、设备改名、安全证据与真实空状态通过 |
| 响应式 | 7 个页面 × 5 个宽度（320/390/768/1280/1440），共 35 项通过；主要页面 5 项 200% 文字放大检查无水平溢出 |
| 真实后端联调 | 独立临时数据库：首次 TOTP 绑定、授权设备、控制接受回执、审计、访客创建/撤销、撤销后拒绝通过；未伪造执行成功 |
| 数据保护 | 升级前备份完成；备份向新的空目录恢复，通过 SQLite 与归档 SHA-256 完整性检查，未覆盖部署数据 |
| Docker 服务 | 新源码镜像部署与重启通过；后端、Web、TLS 健康检查通过，通知进程运行 |
| HTTPS | Python requests 完整 CA/localhost 主机名校验通过；未提供本地 CA 的客户端拒绝证书；未关闭证书验证 |
| 设备 AMD64 镜像 | 构建与离线、无网络、只读运行检查通过；加载 OpenCV/dlib/face-recognition，空帧无人脸、未知执行器及未经签名的设备请求拒绝符合预期 |
| 设备 ARM64 镜像 | GitHub 原生 ARM64 runner 构建、镜像架构断言及无网络/只读离线检查通过；本机跨架构构建随中断停止，没有计为本机通过 |

自动化日志位于本地 `releases/verification`；源码摘要和范围保存在 `verification.json`。管理员页面读取脱敏 `security-report.json`。报告生成时的 Git 基线与实际源码摘要一起标识被检查版本；不会把工作区改动算作旧提交本身。

提交 `2701532` 的 [GitHub Actions 验收](https://github.com/Bearono/smart_lock/actions/runs/37808146394) 已全部成功：backend、frontend、docker、device-image (amd64)、device-image (arm64)。这是远端原生架构软件验收，仍不是 Pi 摄像头与锁具实测。发布包收录脱敏 `verification/ci-report.json`。

浏览器截图位于 `FE_smart_lock/smartlock/test-artifacts`，使用隔离验收数据。截图、备份和依赖目录均不提交；源码发布包包含校验清单和离线报告。协议微基准独立声明 AMD64 环境，不能作为 Pi 性能证据。

算法与完整协议对照的实测表、方法和限制见 [协议微基准记录](HOME_BENCHMARK.md)。

## 可复现入口

从仓库根目录安装后端依赖与 `packages/smartlock_protocol`，在前端执行 `npm ci`，然后运行 `python deploy/verify.py`。浏览器与真实后端联调运行方式见 [交付说明](HOME_DELIVERY.md)。GitHub Actions 配置了相同软件门禁、浏览器验收、Docker HTTP/HTTPS 和设备 AMD64/ARM64 原生构建、架构断言及离线检查。ARM runner 使用 GitHub 官方支持的 `ubuntu-24.04-arm`，依据见 [runner 文档](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)。远端每次运行的状态以对应 Actions 记录为准。

本机界面：http://localhost:8080。受本地 CA 保护的入口：https://localhost:8443。首次使用须创建管理员并绑定 TOTP，没有默认账户。没有登记设备时展示真实空状态。

## 尚须实物验收

真实 Pi 的摄像头驱动、锁具接线与执行器、门磁/锁舌可信反馈、活体算法和误识率，以及 CPU/RSS/温度/推理延时、断网断电恢复，仍须在硬件上完成。当前执行器明确返回未知；软件不会报告未发生的物理成功。

设备 TLS 使用独立服务私钥，需按 Pi 实际地址签发并配置网络；本机证书测试没有替代真实 LAN 验收。python-spake2 的非常数时间限制明确保留，未宣称工业认证。
