# 开发与工程约定

本项目采用单仓库、五个可部署组件和一个共享协议库。组件路径、入口和依赖文件由根目录 `workspace.toml` 声明；`manage.py` 统一调用组件现有工具。

## 环境

- 开发与验收：Python 3.12；统一安装根目录 `requirements-dev.txt`，包含 API 锁定依赖、静态检查及离线 wheel 检查工具。运行镜像仍只安装各组件运行依赖。
- 前端：Node.js 24，使用 `npm ci`。
- Android：JDK 17+、SDK Platform 36、Build Tools 36.0.0；命令行构建无需 Android Studio。
- 原生 Pi：使用系统兼容的 Python、Picamera2/OpenCV 和 `requirements.pi.txt`，不要用通用 pip 包替换系统相机库。
- 容器：Docker Compose v2；ARM64 模拟器需要对应架构或显式配置的仿真支持。

从仓库根目录创建并激活虚拟环境后：

```sh
python -m pip install -r requirements-dev.txt
python -m pip install --no-deps ./packages/smartlock_protocol
npm --prefix apps/web ci
python manage.py check
```

## 模块与变更

模块职责和依赖方向见[系统架构](architecture.md)。前端边界由 ESLint 检查，Python/Android 和目录边界由仓库检查维护。

接口或数据模型变更应同步更新契约、调用方和回归测试。数据库迁移通过维护命令执行，升级步骤与回滚要求写入版本说明。

## 验证分层

| 层           | 命令或入口                                                   | 证明范围                                                   |
| ------------ | ------------------------------------------------------------ | ---------------------------------------------------------- |
| 仓库约束     | `python manage.py check`                                     | 组件、依赖边界、链接和产物隔离                             |
| 通用软件验收 | `python manage.py verify`                                    | Python 全量静态检查/格式、API 回归、Web 单测/静态检查/构建 |
| 浏览器       | Web `test:browser`、`test:integration`、`test:material`      | 布局、状态流转与真实 HTTP 集成                             |
| Android      | `python manage.py android-test --jdk <JDK>`、`android-build` | 主应用 JVM 回归与 APK 构建                                 |
| 设备镜像     | CI 的 amd64/arm64 检查                                       | 架构、导入、模型边界与设备测试                             |
| 实机         | [验证说明](acceptance.md)                                    | 真相机、真人、手机与模拟锁执行                             |

软件夹具、容器和实机结果分别记录，CI 结论对应具体提交。行为变更应有能够发现回归的用例；算法阈值调整需要独立评估和记录。

独立调试界面由 Web 工具链运行浏览器回归：`npm --prefix apps/web run test:device-console` 检查相机控制台，`npm --prefix apps/web run test:lock-simulator` 检查模拟锁面板。两者仅使用隔离夹具，不操作在线设备。

## 文件与配置

- 文件编码 UTF-8；通用文本 LF，Windows cmd/bat 使用 CRLF。Python/Java 使用四空格，Web 与配置使用两空格；Python 统一使用 Ruff，前端统一使用 Prettier。
- 当前文档使用稳定的小写文件名；不保留阶段计划和重复报告，历史通过 Git 追溯。
- 正文网址使用显式 Markdown 链接，配置值使用行内代码；文档变更需核对 GitHub 渲染后的标题、表格、代码块和链接，格式化与链接路径检查不能替代排版检查。
- 数据库、私钥、模板、采集照片、SDK、虚拟环境和构建产物放入被忽略目录。
- `outputs` 用于本机调试证据，`releases` 用于已验证产物，`instance` 用于本机运行状态。
- 配置通过环境变量和显式文件路径注入，不把个人路径、账号或密钥提交到示例。
- Compose 文件保留根目录标准入口；`deploy` 内工具保持稳定，避免目录整理破坏原生 Pi 的部署路径。
- 移除失效入口和未使用实现；保留共享协议所需的教学基线与回归。

## 发布

1. 在选定提交上完成检查并确认 CI 通过，核对版本号和安装签名。
2. 按 [Android 构建指南](../apps/android/README.md)生成 APK，保留 `build-evidence.json`。核对 APK 内配置、证书指纹及 SHA-256。
3. 创建版本标签和 GitHub Release，上传 APK、校验文件及脱敏构建信息。调试签名的联调版本标记为预发布。
4. 版本说明列出变更、Android 要求、服务地址与证书配置、验证结果和升级条件。不得上传签名私钥、设备口令、个人照片或数据库。
5. 发布后用未登录会话下载附件并核对 SHA-256，更新首页下载链接。

如需包含软件检查证据的独立源码包：

```sh
python manage.py verify --output releases/verification
python manage.py package releases/smartlock-source.zip --verification releases/verification
```

发布器验证源码摘要与检查记录一致，回读 ZIP 校验并生成 SHA-256 文件。源码包应能在独立解压目录运行结构检查和构建；个人配置、依赖和运行数据不进入归档。GitHub Release 自动提供标签对应的源码归档。

贡献流程见 [CONTRIBUTING](../CONTRIBUTING.md)。文档按用户操作、开发维护与接口参考组织，信息由对应责任文档维护，历史过程保留在 Git 和 Release 记录中。
