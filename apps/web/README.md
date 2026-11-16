# Web 客户端

Vue 3、TypeScript 和 Vite 构建的响应式门锁界面。客户端使用同源 `/api`；开发代理连接 `127.0.0.1:8000`，部署通过 Nginx 转发。

## 开发

使用 Node.js 24，在本目录执行：

```sh
npm ci
npm run serve
npm test
npm run lint
npm run typecheck
npm run format:check
npm run build
```

依赖版本以 `package-lock.json` 为准。`minimatch` 开发依赖覆盖用于修复 GHSA-g3hv-75wg-m249；修改覆盖前执行依赖审计和前端检查。

## 模块

| 路径                             | 职责                                     |
| -------------------------------- | ---------------------------------------- |
| `src/app`                        | 路由、导航、布局和跨页面门控会话         |
| `src/features`                   | 认证、门控、画面、动态、访客、设置和管理 |
| `src/shared/api`                 | 传输、领域类型和响应校验                 |
| `src/shared/lib`                 | 通用资源生命周期、账户状态和显示格式     |
| `src/shared/ui`                  | 状态、通知、空态、标题、对话框和分页     |
| `src/shared/styles` / `material` | 视觉变量、布局、弹簧交互和玻璃材质       |

权限由后端执行；客户端导航和角色控制仅用于界面呈现。登录与授权令牌不进入 URL 或 Web Storage，私有图片在生命周期结束后释放对象 URL。

## 状态语义

- `reported_status` 为设备最近反馈，`status` 为目标状态，分别展示。
- `executed` 需要确认字段：实体模式检查 `hardware_confirmed`；模拟模式检查 `execution_confirmed`、`simulation_confirmed`，同时要求 `hardware_confirmed=false`。
- 轮询观察窗口为 45 秒。未取得结果时保留原命令查询入口，不自动重新发送控制指令。
- 访客额度在验证并签发授权时扣减；恢复丢失响应使用原凭证。
- 显式时区按偏移解释；历史无时区值标注服务器时间。快照展示接收时间。

## 浏览器测试

先启动前端，再执行确定性夹具测试：

```sh
npx playwright install chromium
npm run test:browser
npm run test:material
npm run test:device-console
```

Windows 可设置 `$env:BROWSER_CHANNEL = 'msedge'` 使用系统 Edge。`FRONTEND_URL` 默认为 `http://127.0.0.1:5173`；截图输出至被忽略的 `test-artifacts/`。

布局验收覆盖七个主页面在 320、390、768、1280 和 1440 像素宽度下的显示，以及空数据、请求失败、长名称、文字放大和窄屏弹窗。检查页面溢出、标签换行、弹窗边界和操作入口；截图需人工复核，自动化结果不替代视觉检查。

真实 HTTP 集成仅连接隔离后端。从仓库根目录启动一个新的夹具进程：

```sh
python apps/api/tests/browser_fixture.py
```

保留前端与夹具进程，在本目录运行：

```powershell
$env:ISOLATED_BACKEND_FIXTURE = '1'
npm run test:integration
```

夹具使用临时数据库，测试覆盖首次 TOTP 登记、会话恢复、命令回执、访客创建和撤销。重复运行前重启夹具，不将此测试指向实际部署。

界面规范见[视觉系统](../../docs/design/visual-system.md)，业务字段见 [API 参考](../../docs/reference/api.md)。
