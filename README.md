# Smart Lock

智能门锁演示项目，包含 Flask 后端、Vue 2 前端、树莓派摄像头网关与人脸识别工具。

## 项目结构

| 目录 | 用途 |
| --- | --- |
| `BE_smart_lock/smart_lock/app` | 数据模型、登录 MFA、设备授权、访客授权、安全通信与日志 |
| `FE_smart_lock/smartlock/src` | 登录、控制台、访客页面与 Axios 接口 |
| `paspberry_pi/app.py` | 设备主入口；监听 5000，处理摄像头与人脸挑战 |
| `paspberry_pi/cv/code` | 人脸录入、128 维特征提取、模板比对及基准测试 |
| `paspberry_pi/cv/code/gateway` | 旧入口兼容包装，调用上面的同一套设备实现 |
| `wanganCV` | 独立人脸实验工具与 FastAPI 检测服务 |
| `BE_smart_lock/smart_lock/tests` | 隔离回归测试与性能工具 |

## 启动后端与前端

建议使用 Python 3.11。不要依赖仓库内历史提交的 `venv`，它包含其他机器的绝对路径。

```powershell
cd BE_smart_lock/smart_lock
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:JWT_SECRET_KEY = '<固定的随机密钥>'
$env:ADMIN_PASSWORD = '<首次启动管理员密码>'
python run.py
```

后端默认 `http://localhost:8000`。启动会创建表、补齐兼容字段及初始化管理员。旧的无设备绑定认证会话、开门令牌、访客码不可继续使用；需重新发起认证或创建访客码。旧 JWT 不含 MFA 登录标记，也必须重新登录。数据库升级前请备份。

```powershell
cd FE_smart_lock/smartlock
npm ci
npm run serve
```

前端通过 `.env.local` 中的 `VUE_APP_API_BASE=http://<后端IP>:8000` 指定后端，视频与 API 使用相同地址。

## 登录和开门

1. 新注册用户为 `pending`，由管理员在 Admin 页面批准。初始管理员用户名默认为 `admin`。
2. `/api/login` 和 `/api/login/pre` 都只返回短期登录挑战。首次登录绑定 TOTP，之后使用 TOTP 完成登录。没有密码直通 JWT 的入口。
3. 登录后绑定目标设备；设备服务的 `SMART_LOCK_DEVICE_ID` 必须与绑定 ID 一致。
4. 发起开门请求，后端保存设备 ID、有效期、nonce 和本次所需因子，再派发人脸挑战。
5. 设备完成识别，通过 SPAKE2 + AES-CBC + HMAC 上报人脸结果。后端核对设备、nonce、身份、分数与有效期。
6. 前端确认认证，获得一次性、绑定设备、60 秒有效的令牌，再调用消费接口。

**令牌签发不等于开门。** 消费成功只表示后端接受开门指令并更新目标状态。当前仓库没有 GPIO 执行器及命令级硬件回执，页面会明确显示硬件执行尚未确认。心跳中的实际状态与后端目标状态分开保存。

夜间 22:00–06:00 创建的认证会话要求额外输入 TOTP；该策略在本次会话有效期内保持不变。连续五次失败锁定对应用户与设备的绑定，解绑重绑不会清除锁定；管理员可解除。解绑会使已有会话、令牌和访客授权失效。

## 设备与人脸录入

```bash
cd paspberry_pi
pip install -r cv/code/gateway/requirements.txt
# 设置 BACKEND_URL、SMART_LOCK_DEVICE_ID、SMART_LOCK_DEVICE_PASSWORD
python app.py
```

```bash
cd paspberry_pi/cv/code
python enroll_face.py --user <后端用户名>
python enroll_face.py --user <后端用户名> --headless --samples 8
```

模板保存到 `paspberry_pi/cv/code/data/templates/templates/`。录入后重启设备服务，或向设备的 `/reload_templates` 发送 POST。用户名必须与后端账号一致，可用 `SMART_LOCK_FACE_ID_MAP=源ID=目标用户名` 配置映射。

摄像头失败默认报错。仅显式设置 `SMART_LOCK_ALLOW_TEST_IMAGES=true` 时才允许设备读取测试图片；这不是活体检测。当前没有实现活体算法。

## 主要配置

| 变量 | 默认 / 用途 |
| --- | --- |
| `DATABASE_URL` | `sqlite:///smart_lock.db`；可指定 MySQL URL |
| `JWT_SECRET_KEY` | 默认随机；稳定运行需固定 |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | `admin` / `admin123`；仅用于管理员初始化 |
| `DEVICE_DISPATCH_REQUIRED` | `true`；设备无法连接则认证请求失败 |
| `SMART_LOCK_DEVICE_URL` | 后端访问设备的固定 URL，优先于心跳 IP |
| `SMART_LOCK_DEVICE_URL_<大写设备ID>` | 单设备 URL 覆盖 |
| `SMART_LOCK_DEVICE_PASSWORD` | 两端共享设备口令；请替换演示默认值 |
| `SMART_LOCK_PASSWORD_<设备ID>` | 后端单设备口令覆盖 |
| `BACKEND_URL` | 设备端访问后端的 URL |
| `SMART_LOCK_DEVICE_ID` | 设备端 ID，默认 `door_01` |

无摄像头联调可设置 `DEVICE_DISPATCH_REQUIRED=false`。**只有连接失败或超时**会留下等待状态；仍必须通过测试客户端提交合法加密人脸结果，不会自动通过人脸认证。设备明确拒绝、识别失败或返回无效响应均失败。模拟测试口令和账号仅用于隔离环境。

目前安全通信会话及防重放缓存为单进程内存结构，多进程部署需要进一步迁移共享会话存储。SQLite 并发写有局限；回归测试覆盖 SQLite 的并发争用，未覆盖 MySQL 部署。默认 `run.py` 是开发服务器。

## 验证

```powershell
cd BE_smart_lock/smart_lock
python -B -m unittest discover -s tests -p 'test_*.py' -v
# 兼容入口：python test_mfa.py
```

测试使用临时 SQLite 数据库和真实 SPAKE2 信封，不连接摄像头、不发送邮件、不修改演示数据库。

```powershell
cd FE_smart_lock/smartlock
npm test
npm run lint -- --no-fix
npm run build
```

接口见 [API_DOCUMENTATION.md](API_DOCUMENTATION.md)，性能工具见 [测试指南](BE_smart_lock/smart_lock/tests/perf/README.md)。历史性能结果不代表修复后的版本，请重新测量。
