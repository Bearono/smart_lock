# SmartLock API

Flask 模块化单体，负责账户、权限、MFA、私有媒体、访客、命令与审计。独立设备协议来自共享包。

- `app/__init__.py`：应用工厂与 HTTP 组件装配。
- `app/extensions.py`：未绑定的数据库和认证扩展，供模型与服务依赖。
- `app/http_hooks.py` / `session_hooks.py`：请求校验、错误契约、健康检查和登录校验。
- `app/routes`：HTTP 契约；MFA 按 credentials、bindings、door、guests 分组。
- `app/door_auth.py`、`face_challenges.py`：认证策略和设备挑战派发。
- `app/secure_payload.py`、`media_ingest.py`：设备信封验证和图片入库。
- 其他业务模块按账户、权限、指令、存储、运维职责命名；不依赖 HTTP 路由。
- `tests`：隔离数据库、协议、权限与发布回归。

从仓库根目录安装 `requirements.txt` 与共享包后运行：

```sh
python -B -m unittest discover -s apps/api/tests -p 'test_*.py' -v
```

本机开发以本目录为工作目录运行 `python run.py`；正式演示使用 [Compose 部署](../../deploy/README.md)。接口与认证说明见 [API 参考](../../docs/reference/api.md)。升级通过维护命令完成，不能在应用启动时隐式修改数据库。
