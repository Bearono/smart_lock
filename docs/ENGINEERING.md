# 工程结构与维护边界

更新日期：2026-11-15。采用四端单仓库与按领域组织的模块化单体；当前课程与单家庭规模无需引入微服务。组件路径和入口由根目录 workspace.toml 声明，manage.py 提供统一操作入口。

| 目录 | 单一职责 |
| --- | --- |
| apps/api/app/routes | HTTP 参数、鉴权入口与响应，不复制密码或设备协议算法 |
| app/accounts、authenticators、passwords、credential_storage | 账户生命周期、一次性 OTP、密码哈希、静态凭据保护 |
| app/authorization、permissions、access_management | 服务端授权和撤销事务 |
| app/door_auth、door_commands、device_commands | 挑战、短期授权、指令与执行回执 |
| app/media_storage、notifications、schema | 私有媒体、持久邮件任务、显式离线升级 |
| apps/web/src/features | auth/home/activity/guests/settings/administration/security 等业务界面 |
| src/shared/api、lib、ui | 类型化接口、内存账户资料、错误呈现和共享组件 |
| packages/smartlock_protocol | 双端共享协议；课程密码、分发与音频实验与生产路径隔离 |
| apps/device | 原生相机、识别与 PAD、设备指令、执行器接口和后台工作线程 |
| apps/android | Android 应用、协议互操作、JVM 测试与 SDK 构建 |
| deploy | 容器、TLS、初始化、备份恢复和检查工具 |
| examples/legacy_crypto | 不安全的历史示例，只供阅读，不进入运行镜像和发布源码包 |
| docs/archive | 历史记录，不能充当当前验收结论 |
| releases | 本机报告与交付产物，Git 忽略 |

## 规则

1. 设备协议复用共享包，禁止前后端各复制一套密码算法或修改后静默降级。
2. 修改权限、账户或密码时同步撤销派生能力；所有执行成功必须来自有效回执与匹配反馈。
3. 领域方法由调用者提交事务；并发一次性消费使用数据库条件更新或唯一约束，不能依赖单进程全局字典。
4. 数据库迁移由维护命令执行，Web worker 启动不隐式修改生产数据。迁移与回滚必须覆盖静态密文文件。
5. 虚拟环境、字节码、采集照片、模板、数据库和私钥不进入当前源码索引；本机依赖不随清理删除。main 跟随当前交付版本，旧提交仍保留在 Git 历史中，因此历史中的秘密不能重新使用。
6. 前端页面不能运行维护命令或持有私钥。公开报告与个人原始证据分开保存。
7. 自动化测试、浏览器夹具、实机测试分层报告，不用假锁状态、假相机图或模拟人脸分数替代硬件结果。
8. 后端与设备需要 Python 3.12，前端使用锁文件与 npm ci。Pi 原生 CSI 依赖系统相机库，不用 pip 覆盖系统 Picamera2/OpenCV；设备镜像和原生 Pi 的依赖配置分别维护。

## 当前结构仍需注意

四个运行端统一位于 apps/api、apps/web、apps/android、apps/device。Docker、原生 Pi 服务模板、CI、自动测试与发布清单使用相同路径；目录边界检查阻止旧入口重新出现。旧本机依赖与实验状态保存在被忽略的 .local/legacy，历史 CV 工具归入 examples/legacy_cv，不进入运行镜像。

前端依赖方向为 app → features → shared，ESLint 禁止 shared 反向依赖业务页面或应用层，也禁止 features 反向依赖 app。界面颜色和材质集中在 shared/styles/tokens.css；页面组合、业务状态、通用组件分别维护。大型 mfa 路由仍承担部分业务编排，继续扩展前应按认证、访客和设备绑定拆分服务。

UI 参考 [Apple iOS 27](https://www.apple.com/os/ios/)、[材质规范](https://developer.apple.com/design/human-interface-guidelines/materials)和[无障碍规范](https://developer.apple.com/design/human-interface-guidelines/accessibility)：内容采用清晰的标准表面，玻璃集中于导航与交互控件，系统增强对比度和减少透明度设置优先于本地外观偏好。Web 实现不依赖 Apple 原生私有组件。

检查入口为 deploy/verify.py、后端 unittest、设备 unittest，以及前端 test:browser / test:integration。网络依赖审计是额外检查，不能用其结果替代代码审查。远程 CI 的通过记录只对具体提交有效。
