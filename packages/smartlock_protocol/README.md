# smartlock-protocol

API 与树莓派共同安装的 Python 包，不依赖 Flask 或应用内部模块。

| 模块 | 职责 |
| --- | --- |
| `v3` | 当前设备会话、密钥确认、AES-GCM 信封 |
| `command_auth` | 设备与模拟执行器命令的认证格式 |
| `v2` | 显式保留的旧协议教学基线；生产拒绝降级 |
| `course_lab` / `distribution_lab` / `rsa_math` | 独立课程密码实验 |

```sh
python -m pip install --no-deps ./packages/smartlock_protocol
```

依赖由调用组件锁定安装。包发现仅包含 `smartlock_protocol` 命名空间，禁止把本机 build、测试或其他目录打入 wheel。协议修改必须运行双端兼容、篡改、重放和旧版本拒绝测试。

教学算法和实验代码不应被当作可替代生产协议的入口。
