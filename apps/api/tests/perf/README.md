# 性能与端到端验证

这里的脚本只用于隔离测试环境，会创建测试账号、绑定设备并改变测试设备的目标状态。
历史 `results/` 来自旧版认证流程，不能用于证明当前版本通过测试或衡量当前性能。

## 准备

1. 在隔离数据库启动后端，安装后端 requirements 及 `locust matplotlib`。
2. 设定相同的 `PERF_TOTP_SEED`，运行 `python tests/perf/prepare_data.py`。
3. 默认创建 `perf_user_001`–`020`，密码由 `PERF_USER_PASSWORD` 控制，绑定 `PERF_DEVICE_ID`（默认 `door_01`），并启用测试 TOTP。

测试 TOTP 是由测试 seed 和用户名派生的可重复凭证，仅供这些测试账号使用。不要给真实用户使用该 seed；测试工具没有关闭服务端 MFA。

## 端到端

真实网关：

```powershell
python tests/perf/measure_e2e.py --runs 30
```

无摄像头的隔离模拟：后端设置 `DEVICE_DISPATCH_REQUIRED=false`，并把测试设备 URL 指向没有服务的地址；客户端设置与后端一致的 `SMART_LOCK_DEVICE_PASSWORD`。

```powershell
python tests/perf/measure_e2e.py --simulate-face --runs 30
```

测量链路：密码 + TOTP 登录 → 发起挑战 → SPAKE2 与加密人脸上报 → MFA 确认 → 消费令牌。
夜间自动使用测试账号 TOTP。真实网关的识别包含在 `open_request` 中，`face_result` 单列为 0，避免重复发送和双计时；模拟模式将握手及加密上报计入 `face_result`。

只有全部阶段成功且消费得到 `command_accepted=true` 才计为有效样本。任一失败使脚本最终退出码非零，不能把 400/401 或令牌消费失败作为成功。结果是后端指令接受时延，不包含 GPIO 执行时间。

## Locust

```powershell
.\tests\perf\run_perf.ps1
.\tests\perf\run_perf.ps1 -LoginOnly
```

```bash
bash tests/perf/run_perf.sh
LOGIN_ONLY=1 bash tests/perf/run_perf.sh
```

默认选 `SmartLockUser`；`LoginOnlyUser` 测完整密码/TOTP 两步登录。读接口保持原权重，控制写接口只发送 LOCK。开门请求出现 403/423/502 均计失败。

单独调用 Locust 时应显式指定 User 类：

```bash
locust -f tests/perf/locustfile.py SmartLockUser --headless -u 10 -r 5 -t 2m --host http://localhost:8000
```

`SmartLockUser` 中开门请求只测请求创建/派发，不代表全链路成功；完整链路使用 `measure_e2e.py`。
汇总命令仍为 `python tests/perf/aggregate_results.py --plot`，产出 CSV/Markdown/PNG。

## 回归与 CV

```powershell
python -B -m unittest discover -s tests -p 'test_*.py' -v
```

回归测试独立创建临时 SQLite，不依赖测试账号或运行中的后端。前端在前端目录运行 `npm test`。

CV 基准在 `paspberry_pi/cv/code` 执行：

```bash
python bench_recognize.py --source image --path test.jpg --frames 100
```

检测、embedding、模板匹配分别计时。没有人脸的帧会跳过；基准不能替代识别准确率、活体或硬件开门测试。
