# SmartLock Web

Vue 3 + TypeScript + Vite 智能家居门锁界面，使用同源 `/api`。开发代理目标为 `127.0.0.1:8000`，生产镜像通过 Nginx 转发。Node 至少 22.12，部署镜像使用 Node 24。

## 开发与检查

```sh
npm ci
npm run serve
npm test
npm run lint
npm run typecheck
npm run format:check
npm run build
```

## 结构与职责

- `app/`：应用装配、导航、路由、账户入口，以及跨页面保留的命令回执。
- `features/`：按认证、我的家、开门、摄像头、动态、访客、设置、管理与安全证据组织。
- `features/door/useDoorSession.ts`：登录布局持有的开门会话；敏感凭证只在内存存在。
- `features/guests/guestFlow.js`：可独立测试的访客验证与原命令恢复流程。
- `shared/lib/useResource.ts`：带类型的请求代次控制，旧响应与卸载后响应不会覆盖界面。
- `features/camera/usePrivateImage.js`：私有图片获取、代次控制及对象 URL 回收。
- `shared/ui/`：语义化状态、通知、空状态、标题、原生模态对话框、分页与原创家门插画。
- `shared/styles/`：燕麦白/陶土色设计变量、布局、响应式和减少动态效果规则。
- `shared/api/`：TypeScript 传输接口、领域数据类型和设备/快照运行时校验。

所有权限由后端执行。客户端的导航与路由角色控制只改善体验，不能作为授权依据。生产页面不连接测试数据。

## 状态约定

- `reported_status` 是最近上报状态，`status` 是目标状态；界面不能将目标状态当成实际状态。
- 命令受理、身份验证通过和设备执行确认分别展示。只有 `executed` 且 `hardware_confirmed === true` 才显示执行确认。
- 命令轮询观察窗口为 45 秒，查询超时保持结果未知；可只读查询原命令，不自动重发控制。
- 结果未知时，用户核查现场后可明确结束跟踪；此操作不撤销命令，也不将未知改成成功。
- 访客 `used_count` 在验证、签发授权时扣减，界面称“验证额度”，不称成功开门次数。
- 时间字段目前未携带时区，界面保留服务器时间，不进行隐含时区转换。快照未提供拍摄时间，不能标为实时视频。
- 报警查询最近最多 100 条；操作审计和人脸日志分别分页，不伪造统一设备时间线。
- 设备授权每行单独生效；已有授权但未上报的设备仍在权限详情中显示。
- 登录、开门、访客令牌、TOTP 密钥不进入 URL 或新增持久化存储。退出和页面销毁清理内存凭证及私有图片。

## 浏览器验收

先启动前端。测试脚本拦截 `/api/` 根路径，使用独立确定性夹具，不访问真实门禁设备、不修改后端数据库。

```sh
npx playwright install chromium
npm run test:browser
```

也可使用系统 Edge，在 PowerShell 中执行：

```powershell
$env:BROWSER_CHANNEL = 'msedge'
$env:FRONTEND_URL = 'http://127.0.0.1:5173'
npm run test:browser
```

覆盖登录、丢失消费响应恢复、跨页面命令跟踪、上报状态与回执分离、无效 TOTP、权限提交失败、访客创建/撤销、报警详情、手机导航及 320/390/768/1280/1440px 下六个业务页面。浏览器运行错误或 Vue 警告会使验收失败。截图输出到已忽略的 `test-artifacts/`。

Node 测试覆盖真实业务模块和命令跟踪，包括重复点击、凭证保留、响应丢失、未知结果及卸载后的迟到响应。模拟浏览器验收不替代真实设备端验证。

## 隔离真实后端验收

从仓库根目录显式运行：

```sh
python BE_smart_lock/smart_lock/tests/browser_fixture.py
```

夹具只在 `127.0.0.1:8000` 监听，数据库和图片保存在临时目录。测试账户 `qa_operator`、密码 `local-qa-password`，首次登录按页面显示的密钥绑定 TOTP。该脚本不参与生产初始化。真实后端的认证和命令受理可在此前端页面检查；夹具没有合成的人脸成功与执行确认。

启动一个全新的夹具及前端后，可执行自动集成验收。此测试会登记 TOTP、提交命令、创建并撤销访客凭证，只能用于夹具的临时数据库；不可指向真实部署。

```powershell
$env:ISOLATED_BACKEND_FIXTURE = '1'
$env:BROWSER_CHANNEL = 'msedge'
npm run test:integration
```

集成测试验证真实接口中的首次 TOTP 绑定、授权设备列表、上锁命令受理、审计记录、访客创建/撤销和已撤销凭证拒绝。首次登记是一次性动作，重复运行前必须重新启动夹具。

## 当前接口边界

网页未提供人脸登记接口；账户页明确说明现有维护方式。设备名称已持久化，新控制日志关联命令，快照显示服务器接收时间，后端在明确时区后输出偏移。没有可信设备拍摄时间，历史未关联记录不猜测设备；报警仍是最多 100 条筛选结果。
