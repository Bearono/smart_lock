# 家门体验与安全协议交付

本轮将项目从门禁控制台改为智能家居门锁与摄像头界面。适用于电子科技大学大三软件工程网络安全方向综合设计，目标硬件 Raspberry Pi 4B / 2 GB。方案依据保留在 `COURSE_PROJECT_DESIGN_PLAN.md`，这里说明实际实现与复现方法。

## 使用界面

- 我的家：欢迎区域、当前家门、最近连接与锁状态、门前私有快照、身份验证及命令回执。没有真实快照时显示空状态，不伪造现场画面或直播。
- 动态：按日期阅读操作与人脸验证。新控制记录关联设备与命令；历史未关联记录明确说明。提交记录不表示执行成功。
- 访客：名称、有效期限、验证额度、一次性展示完整凭证、撤销及独立公开验证页。
- 设置：身份验证器、设备认证绑定、密码修改；管理员可以持久化家门名称并留下审计。
- 管理入口：异常提醒、成员与权限、安全证据。普通成员由路由与后端共同限制进入管理员功能，最终权限由后端强制执行。

燕麦白背景、暖纸卡片、陶土主按钮与柔和绿状态统一覆盖登录、访客、业务和管理页面。移动端四个底部入口，桌面浅色导航。减少动态效果、键盘焦点、原生对话框与图片代次回收保留。

## 代码边界

前端 `src/app` 管理应用装配、布局和路由；`src/features` 按认证、家门、开门、摄像头、动态、访客、设置、管理与证据划分；`src/shared` 存放接口契约、公共 UI、资源加载和设计变量。页面采用 TypeScript；开门会话由登录布局持有，路由切换不会遗失正在跟踪的命令。少量既有纯 JavaScript 流程和回执组件保留其独立行为测试，TypeScript 并存配置中不假称这些模块已开启严格 JS 检查。

网络边界对设备和快照做运行时校验：未知锁状态不会显示已锁，异常电量不会显示百分比，私有图片路径必须符合受控路径。Vue 类型检查不代替 HTTP 数据校验。

后端采用加法迁移，新增 `devices.display_name`、控制日志设备/命令关联、协议版本和确认状态，不猜测历史记录的关联。已有墙钟时间只有在显式配置 `SMART_LOCK_SERVER_TIMEZONE` 后才附加时区。Compose 的既有容器时钟为 UTC，因此声明 UTC；迁移其他来源数据库时必须配置原来的时区，不能照抄这个值。

## 安全协议与迁移

`packages/smartlock_protocol` 是后端、设备与历史 v2 入口共享的协议源码包。开发环境先安装后端依赖，再执行 `pip install --no-deps ./packages/smartlock_protocol`。两种 Docker 镜像均安装同一个本地包。

v3 基于现有 SPAKE2 教学基线，握手 transcript 绑定发起消息、版本、会话、双方消息、nonce 与期限，并通过服务端证明、客户端确认和确认回执完成双向密钥确认。确认前的会话无法执行业务。设备拒绝 v2 响应，不自动降级。当前 Compose 设置 `SMART_LOCK_ALLOW_PROTOCOL_V2=false`；需要受控迁移时可显式开启，开发测试保留 v2 对照。

AES-256-GCM 信封的 AAD 包含版本、会话、设备、请求 ID、时间、nonce、方法、完整端点和方向。HKDF 分离会话、确认、设备请求加密和服务端命令响应认证用途。命令同步响应认证完整原请求上下文。nonce 在每个新会话中由线程安全的 96 位计数器分配；设备进程重启重新握手，禁止持久化并恢复旧客户端密钥/计数器。服务端数据库保存加密会话密钥与唯一重放凭据，服务重启不会允许旧消息再次执行。

python-spake2 不承诺常数时间实现；TLS 和 AEAD 没有消除这个限制。不能把课程实现宣称为经认证的工业门锁产品。公网产品应采用经审查的认证实现、设备凭据生命周期与完整安全评估。

## 部署与查看

普通本机预览：`docker compose up -d --build --wait`，打开 http://localhost:8080。第一次管理员账户须执行 `docker compose exec backend flask --app run create-admin --username operator`，交互设置密码并绑定 TOTP；没有默认密码。不要向实际部署注入验收用账户或虚构设备。

局域网课程演示可执行：

```sh
python deploy/init_local_tls.py --host 你的电脑局域网IP
docker compose -f compose.yaml -f compose.tls.yaml up -d --wait
```

本机 HTTPS 入口 https://localhost:8443。脚本只生成本地演示 CA，拒绝覆盖已有密钥；私钥位于忽略版本控制的 `deploy/tls`。客户端只安装/配置 `ca.crt`，不得复制 CA 私钥。远程访问还须显式设置 `SMART_LOCK_TLS_BIND_IP`、防火墙和正确地址，证书 SAN 必须包含该地址。公开部署用正常可信证书替换演示证书。TLS 容器探针检查进程和证书配置，上游 Web 探针检查服务；额外用客户端的完整 CA/主机名验证检查 HTTPS 请求。

TLS 网关只挂载服务证书和服务私钥，不挂载 CA 私钥。HTTPS API 直接转发后端，入口覆盖客户端地址头，避免多层代理把所有客户端归到同一个限流地址。nonce 重放凭据保留至会话密钥过期，时间窗口结束不会提前释放同一密钥下的 nonce。

树莓派 `BACKEND_URL` 必须是设备可达的 HTTPS 地址。`compose.device.yaml` 挂载 `deploy/tls/ca.crt` 并设置 `SMART_LOCK_CA_BUNDLE`；使用公开证书时改为系统/组织信任库并相应调整挂载。生产设备拒绝 HTTP 地址。不得设 `verify=false`。

反向设备服务也有独立 TLS 入口：在电脑执行 `python deploy/issue_device_tls.py --host 树莓派IP`，只把 `device.crt`、`device.key`、`ca.crt` 复制到 Pi 对应 `deploy/tls`（不要复制 CA 私钥）。在 Pi 设置 `DEVICE_TLS_BIND_IP` 后执行 `docker compose -f compose.device.yaml -f compose.device.tls.yaml up -d --wait`，后端登记服务 URL 为 `https://树莓派IP:8443`。电脑的 TLS override 已挂载 CA 并通过 `REQUESTS_CA_BUNDLE` 校验设备 HTTPS。设备与后端使用不同服务私钥；此配置仍须在真实网络、真实 Pi 验收。默认本机 HTTP 设备入口只监听回环地址。

## 验收与报告

`python deploy/protocol_benchmark.py` 生成隔离的算法微基准：原始 AES-GCM/ChaCha20-Poly1305 与完整 v2/v3 信封分别标注，不把裸算法与完整协议当同一种测量。报告保存体系结构和环境；在当前电脑生成的结果只能说明当前电脑，Pi 性能须在 Pi 上运行此工具后记录。

前端：`npm ci`、`npm run lint`、`npm run typecheck`、`npm test`、`npm run format:check`、`npm run build`。浏览器测试通过 `npm run test:browser` 运行；须启动 Vite，设置 `FRONTEND_URL`，本机已有 Edge 可设置 `BROWSER_CHANNEL=msedge`。真实后端集成使用 `tests/browser_fixture.py` 的独立临时数据库，必须设置 `ISOLATED_BACKEND_FIXTURE=1`，禁止拿生产数据库代替。

全套软件报告：`python deploy/verify.py`。生成 `releases/verification/verification.json` 及经过筛选的 `security-report.json`，包含生成时间、环境、Git 基线、实际源码摘要、范围和检查结果。工作区源码摘要用于标识尚未提交的变化，Git SHA 本身不代表这些变化。浏览器、Docker、硬件不包含在这份软件报告范围内。

把脱敏摘要放入后端 `/data/security-report.json`，或配置 `SMART_LOCK_SECURITY_REPORT_PATH`，管理员证据页才能展示。报告是生成时的记录，网页不运行测试、不读取密钥、不提供攻击按钮，也不把数据库数量当安全评分。源报告缺失或损坏显示未提供。

发布包通过 `python deploy/package_release.py releases/smart-lock-home.zip` 生成；先有同一源码的成功验证报告。包采用允许名单，包括 TS、CSS、共享协议、部署和课程资料；不包含数据库、人脸模板、密钥、依赖目录。升级前停止写入并用 `deploy/backup.py` 创建备份，恢复到空目录，保留应用密钥另行保护。

## 树莓派实机验收边界

设备保持单 worker、两条请求线程、有限连接 backlog、串行采集和串行推理/模板更新，避免模型重复加载及 OpenCV 网络并发读写。OpenBLAS/OMP 限制为一条线程；V4L2 请求 640×480，实际分辨率仍由硬件协商决定。1200 MB 容器上限是保护值，不是实测占用。

本机软件测试与 x86 容器构建不能替代 Pi ARM64 实测。仍需在实物确认摄像头型号、CSI/V4L2 驱动、锁具执行接口和可信状态反馈；当前 `UnavailableActuator` 会报告未知并拒绝伪造执行成功。必须记录板上冷启动、推理时延、RSS、CPU、温度、降频、断网恢复和重复命令结果。没有接入实物时，这一验收不能宣称完成。

## 答辩演示顺序

1. 登录并说明密码与 TOTP 两阶段身份验证；显示真实家门与最近画面。
2. 提交上锁/验证开门，区分接受回执、执行回执和设备上报；断网时展示原命令查询与未知结果处理。
3. 创建访客、撤销后在公共页验证拒绝；管理员审批与设备授权相互独立。
4. 展示新日志的设备/命令关联以及管理员设备改名审计。
5. 展示 v3 上下文绑定、持久重放防护、隔离测试报告及其源码摘要，说明 python-spake2 和未接入硬件的限制。
