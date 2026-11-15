# 开发与工程约定

本项目采用单仓库、五个可部署组件和一个共享协议库。组件路径、入口和依赖文件由根目录 `workspace.toml` 声明；`manage.py` 统一调用组件现有工具。

## 环境

- 后端及通用工具：Python 3.12；安装 `apps/api/requirements.txt`（约束来自同目录锁文件）。
- 前端：Node.js 24，使用 `npm ci`。
- Android：JDK 17+、SDK Platform 36、Build Tools 36.0.0；命令行构建无需 Android Studio。
- 原生 Pi：使用系统兼容的 Python、Picamera2/OpenCV 和 `requirements.pi.txt`，不要用通用 pip 包替换系统相机库。
- 容器：Docker Compose v2；ARM64 模拟器需要对应架构或显式配置的仿真支持。

从仓库根目录创建并激活虚拟环境后：

```sh
python -m pip install -r apps/api/requirements.txt
python -m pip install --no-deps ./packages/smartlock_protocol
npm --prefix apps/web ci
python manage.py check
```

## 源码边界

| 层 | 允许的依赖与职责 |
| --- | --- |
| Web `app` | 组装路由、布局和跨页面状态，可依赖 features/shared |
| Web `features` | 业务界面与流程，可依赖 shared，不反向依赖 app |
| Web `shared` | 通用类型、传输、组件与视觉变量，不依赖业务页面 |
| API `routes` | HTTP 输入、身份校验、响应和服务编排 |
| API 业务模块 | 账户、权限、授权、命令、媒体与存储规则 |
| Device | 相机与模型资源、设备会话、命令执行和反馈 |
| Lock simulator | 独立锁状态、故障模拟与持久指令去重 |
| Shared protocol | 不依赖 Flask、Vue 或应用模块的协议实现 |
| Android `src/main` | 门锁客户端；实验代码位于 examples，不进入 APK |

保持已验证的模块化单体和设备边界。跨端协议只在共享包实现；应用不得引用另一应用的内部实现或测试夹具。前端边界由 ESLint 检查，Python/Android 和目录边界由仓库检查维护。涉及数据模型或接口调整时同时更新契约、调用方与回归测试。

API 领域方法的事务由调用方统一提交；一次性授权使用数据库条件更新/约束。数据库升级通过维护入口执行，不能在 Web worker 启动时隐式改表。设备服务维持一个 worker，执行回执必须来自驱动反馈，不能由前端按钮或目标状态推断。

## 验证分层

| 层 | 命令或入口 | 证明范围 |
| --- | --- | --- |
| 仓库约束 | `python manage.py check` | 组件、依赖边界、链接和产物隔离 |
| 通用软件验收 | `python manage.py verify` | API 全量回归、Web 单测/静态检查/构建 |
| 浏览器 | Web `test:browser`、`test:integration`、`test:material` | 布局、状态流转与真实 HTTP 集成 |
| Android | `python manage.py android-test --jdk <JDK>`、`android-build` | 主应用 JVM 回归与 APK 构建 |
| 设备镜像 | CI 的 amd64/arm64 检查 | 架构、导入、模型边界与设备测试 |
| 实机 | [验收范围](acceptance.md) | 真相机、真人、手机与模拟锁执行 |

软件夹具与真实设备证据分开记录；不调整认证阈值来凑成功结果。CI 结论只对应具体提交。按照改动范围执行检查，行为改变应有能够发现回归的用例。

## 文件与配置

- 文件编码 UTF-8；通用文本 LF，Windows cmd/bat 使用 CRLF。Python/Java 使用四空格，Web 与配置使用两空格。
- 当前文档使用稳定的小写文件名；日期记录只进入 `docs/archive`。
- 数据库、私钥、模板、采集照片、SDK、虚拟环境和构建产物放入被忽略目录。
- `outputs` 用于本机调试证据，`releases` 用于已验证产物，`instance` 用于本机运行状态。
- 配置通过环境变量和显式文件路径注入，不把个人路径、账号或密钥提交到示例。
- Compose 文件保留根目录标准入口；`deploy` 内工具保持稳定，避免目录整理破坏原生 Pi 的部署路径。
- 历史音频与密码实验具有独立入口，保留回归用例，不成为门锁运行依赖。

## 发布

运行 `python manage.py verify --output releases/verification`，再执行：

```sh
python manage.py package releases/smartlock-source.zip --verification releases/verification
```

发布清单包含组件源码、构建配置、静态资源、测试和工程文档，排除本机状态及历史不安全示例。发布器核对源码摘要，回读 ZIP 校验，并生成 SHA-256 文件。解压包应可脱离 Git 仓库运行结构检查；不能只在开发者工作区验证成功。

贡献流程见 [CONTRIBUTING](../CONTRIBUTING.md)。目录规则参考 [Gradle 的源码集合约定](https://docs.gradle.org/current/userguide/organizing_gradle_projects.html)、[PyPA 的包布局说明](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/)；依据本项目现有部署约束选择布局，不增加无用的服务或中间层。
