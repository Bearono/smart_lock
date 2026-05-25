# Smart Lock

智能门锁摄像头项目，包含后端服务、前端界面、树莓派端网关/摄像头程序以及人脸识别相关代码。项目支持账号登录、TOTP 多因素认证、设备绑定、摄像头人脸校验、开门令牌、访客通行码、告警记录、设备心跳和门锁状态管理。

本项目用于智能门锁摄像头系统的本地开发、联调与功能演示。

## 目录结构

```text
.
├── BE_smart_lock/              # 后端 Flask 服务
│   └── smart_lock/
│       ├── app/                # 应用代码、模型、路由
│       ├── config.py           # 后端配置
│       ├── requirements.txt    # Python 依赖
│       └── run.py              # 后端启动入口
├── FE_smart_lock/              # 前端项目
│   └── smartlock/              # Vue 2 前端源码
├── paspberry_pi/               # 树莓派端摄像头/网关代码
├── wanganCV/                   # 人脸识别相关代码
└── API_DOCUMENTATION.md        # 前后端接口文档
```

## 技术栈

- 后端：Flask、Flask-SQLAlchemy、Flask-JWT-Extended、Flask-Bcrypt、PyMySQL、pyotp、cryptography
- 前端：Vue 2、Vue Router、Axios、Vue CLI
- 数据库：默认 SQLite，支持通过 `DATABASE_URL` 切换到 MySQL
- 设备端：树莓派摄像头采集、人脸识别结果上报、门锁控制联动

## 后端启动

进入后端目录：

```powershell
cd BE_smart_lock\smart_lock
```

创建并激活 Python 虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

安装依赖：

```powershell
pip install -r requirements.txt
```

启动服务：

```powershell
python run.py
```

默认监听地址：

```text
http://localhost:8000
```

后端启动时会自动创建数据库表。默认数据库文件为 Flask instance 目录下的 `smart_lock.db`。

## 后端环境变量

| 变量名 | 说明 | 默认值 |
| --- | --- | --- |
| `DATABASE_URL` | 数据库连接地址，例如 MySQL 可使用 `mysql+pymysql://user:password@host:3306/dbname?charset=utf8mb4` | `sqlite:///smart_lock.db` |
| `JWT_SECRET_KEY` | JWT 签名密钥，生产环境必须固定配置 | 随机生成 |
| `DEVICE_DISPATCH_REQUIRED` | 人脸挑战下发失败时是否直接报错。联调阶段建议 `false`，无树莓派也可走通流程 | `false` |
| `SMART_LOCK_DEVICE_URL` | 默认设备端服务地址，用于后端下发人脸挑战 | 空 |
| `SMART_LOCK_DEVICE_URL_<DEVICE_ID>` | 指定设备的服务地址，例如 `SMART_LOCK_DEVICE_URL_LOCK_1` | 空 |

联调阶段如果还没有树莓派端服务，可以保持：

```powershell
$env:DEVICE_DISPATCH_REQUIRED = "false"
```

这样 `/api/mfa/open-door/request` 在设备派发失败时会走开发兜底，方便前端先完成流程联调。正式接入设备后建议改为：

```powershell
$env:DEVICE_DISPATCH_REQUIRED = "true"
```

## 前端启动

进入前端目录：

```powershell
cd FE_smart_lock\smartlock
```

安装依赖：

```powershell
npm ci
```

启动开发服务：

```powershell
npm run serve
```

构建生产包：

```powershell
npm run build
```

前端默认请求后端：

```text
http://localhost:8000
```

如需修改后端地址，可在前端目录创建 `.env.local`：

```text
VUE_APP_API_BASE=http://localhost:8000
```

## 常用联调流程

1. 启动后端：`BE_smart_lock\smart_lock\run.py`
2. 启动前端：`FE_smart_lock\smartlock` 下执行 `npm run serve`
3. 前端注册用户：`POST /api/register`
4. 首次登录走预登录：`POST /api/login/pre`
5. 按返回的 TOTP 密钥绑定 MFA：`POST /api/login/mfa/bind`
6. 登录后绑定设备：`POST /api/mfa/bind/device`
7. 发起开门认证：`POST /api/mfa/open-door/request`
8. 确认开门并获取开门令牌：`POST /api/mfa/open-door/confirm`

完整接口字段请查看 [API_DOCUMENTATION.md](./API_DOCUMENTATION.md)。

## 代码检查

后端基础检查：

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONPATH = "BE_smart_lock\smart_lock"
python -B -c "from app import create_app; app = create_app(); print('app created', len(app.url_map._rules))"
```

前端构建检查：

```powershell
cd FE_smart_lock\smartlock
npm ci
npm run build
```

## 注意事项

- 不要提交 `__pycache__`、`.pyc`、`node_modules`、`dist`、`outputs`、IDE 配置等生成文件。
- 后端默认开启 CORS，便于本地前后端分端口联调。
- 当前前端使用 Vue 2，安装依赖时可能出现 Vue 2 EOL 或依赖漏洞提示，联调可先忽略，后续可单独规划升级。
- 生产环境必须配置固定的 `JWT_SECRET_KEY`，并将 `DEVICE_DISPATCH_REQUIRED` 设置为 `true`。
