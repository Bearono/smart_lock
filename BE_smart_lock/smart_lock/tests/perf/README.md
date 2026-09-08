# 智能锁性能测试指南

本目录提供一整套开箱即用的性能测试脚本，覆盖 **接口负载**、**端到端时延**、**人脸识别推理** 三个维度，产出的 CSV / Markdown / PNG 可以直接贴进报告。

## 目录结构

```text
tests/perf/
├── locustfile.py          # Locust 压测脚本 (核心接口 + LoginOnly 场景)
├── prepare_data.py        # 批量创建 perf_user_001~020 并绑定测试设备
├── measure_e2e.py         # 端到端开门流程时延测量 (阶段拆分)
├── aggregate_results.py   # 汇总各档 Locust CSV, 生成表格 + 曲线图
├── run_perf.ps1           # Windows 一键运行
├── run_perf.sh            # Linux/macOS 一键运行
└── results/               # 所有产出都落在这里
```

另外在 `paspberry_pi/cv/code/bench_recognize.py` 有 CV 推理基准脚本。

## 一、准备工作

### 1.1 安装依赖

在后端虚拟环境里补装两个包：

```powershell
cd BE_smart_lock\smart_lock
.\venv\Scripts\Activate.ps1
pip install locust matplotlib
```

### 1.2 启动后端

**关键：** 联调阶段务必关闭真实设备派发，让 `/open-door/request` 走开发兜底，否则压测会因为找不到树莓派而全部报错。

```powershell
$env:DEVICE_DISPATCH_REQUIRED = "false"
$env:ADMIN_USERNAME = "admin"
$env:ADMIN_PASSWORD = "admin123"
python run.py
```

后端监听 `http://localhost:8000`。

### 1.3 生成测试账号

在**另一个终端**里跑：

```powershell
cd BE_smart_lock\smart_lock
.\venv\Scripts\Activate.ps1
python tests\perf\prepare_data.py
```

会创建 `perf_user_001` ~ `perf_user_020`（口令 `Perf@123456`），直接置为 approved，并给每个账号绑定测试设备 `door_01`；同时兜底写入 30 条访问日志和人脸识别日志，让分页接口有数据可读。

跑完后清理：`python tests\perf\prepare_data.py --cleanup`。

## 二、接口负载测试 (Locust)

### 2.1 一键跑

```powershell
.\tests\perf\run_perf.ps1                    # 10 / 50 / 100 并发, 每档 2 分钟
.\tests\perf\run_perf.ps1 -Duration 3m       # 每档 3 分钟
.\tests\perf\run_perf.ps1 -LoginOnly         # 单独测 /api/login (bcrypt)
```

Linux / Git Bash：

```bash
bash tests/perf/run_perf.sh
DURATION=3m CONCURRENCIES="20 60 120" bash tests/perf/run_perf.sh
LOGIN_ONLY=1 bash tests/perf/run_perf.sh
```

每档结束后会生成：

```text
results/c10_stats.csv           每接口聚合结果
results/c10_stats_history.csv   时序数据
results/c10_failures.csv        失败明细
results/c10.html                Locust 官方 HTML 报告 (报告截图直接用)
```

### 2.2 汇总出图

```powershell
python tests\perf\aggregate_results.py --plot
```

产出：

- `summary_by_endpoint.csv` —— 每接口 × 每档一行，Excel 打开直接排版
- `summary_by_endpoint.md` —— Markdown 表格，报告里 Ctrl-V 就行
- `perf_curves.png` —— 两张子图：P95 响应时间 vs 并发、QPS vs 并发

### 2.3 覆盖的接口

`locustfile.py` 里给不同接口配了权重，模拟真实使用比例：

| 权重 | 接口 | 说明 |
|---|---|---|
| 8 | GET /api/lock/status | 最常见的轮询接口 |
| 6 | GET /api/lock/history | 分页查询 |
| 4 | GET /api/mfa/status | MFA 状态 |
| 3 | GET /api/device/status | 设备在线状态 |
| 2 | GET /api/face/logs | 人脸识别日志 |
| 2 | GET /api/alarms | 告警列表 |
| 2 | POST /api/lock/control | 门锁翻转 |
| 1 | POST /api/mfa/open-door/request | 开门发起 |
| — | POST /api/login | 每次虚拟用户上线时执行一次 |

如果要单独强调**登录性能**（bcrypt 是慢点），用 `LoginOnly` 场景：并发全部打在 `/api/login` 上。

## 三、端到端时延测试

单线程串行跑完整开门流程，把总耗时拆到 5 个阶段：

```text
login         POST /api/login             登录（含 bcrypt 校验）
open_request  POST /api/mfa/open-door/request     会话创建 + 设备派发/兜底
face_result   POST /api/mfa/open-door/face-result  人脸结果回传（模拟）
confirm       POST /api/mfa/open-door/confirm      汇总因子, 签发 unlock_token
token_verify  POST /api/lock/unlock-token/verify   硬件消费, 门锁翻转
```

跑法：

```powershell
python tests\perf\measure_e2e.py --runs 30
```

产出：

- `results/e2e_stages.csv` —— 每次运行各阶段耗时明细
- `results/e2e_summary.csv` —— 均值/中位数/P95/标准差

报告里画一张**阶段耗时堆叠柱状图**（Excel 一分钟能做）说明哪一步是瓶颈；再画一张**总耗时分布直方图**说明稳定性。

## 四、人脸识别推理性能测试

在树莓派上（或 PC 上）跑：

```bash
cd paspberry_pi/cv/code
python bench_recognize.py --source image --path test.jpg --frames 200
# 或用摄像头
python bench_recognize.py --source camera --frames 100
# 或跑一个目录里的所有图片
python bench_recognize.py --source dir --path ../outputs/faces --frames 100
```

分三个阶段计时：

- `detect` —— DNN 人脸检测
- `embedding` —— 特征向量提取
- `match` —— 与模板库余弦相似度比对

产出：

- `bench_results/bench_stages.csv`
- `bench_results/bench_summary.csv`（附带 FPS 估算）

**报告建议**：树莓派上和 PC 上各跑一次，对比表格里放 `mean / P95 / FPS` 三列，直观体现算力差异。

## 五、报告里怎么用这些数据

| 报告章节 | 用哪份数据 | 图表建议 |
|---|---|---|
| 后端接口性能 | `summary_by_endpoint.md` + `perf_curves.png` | 表格 + 双曲线图 |
| 登录性能专项 | `LoginOnly` 场景的 `c*.html` | 截 Locust 自带图 |
| 端到端开门时延 | `e2e_summary.csv` | 阶段堆叠柱状图 + 直方图 |
| 人脸识别推理 | `bench_summary.csv` | 阶段占比饼图 + FPS 表格 |
| 结论 | 综合以上 | 瓶颈定位 + 优化方向 |

## 六、常见问题

**Q: Locust 大量报 403 `Device not bound`?**
A: 先跑 `prepare_data.py`。或者手动改 `PERF_DEVICE_ID` 环境变量指向已绑定的设备。

**Q: 深夜跑测试 confirm 报 400 `TOTP code required`?**
A: 后端 `evaluate_mfa_policy` 在 22:00-06:00 会要求 TOTP。要么白天跑，要么临时把 `mfa.py` 里的时间判断改成 `False`。

**Q: `/open-door/request` 全部 502?**
A: 你把 `DEVICE_DISPATCH_REQUIRED` 设成了 `true`，但没有树莓派。改成 `false` 走开发兜底。

**Q: SQLite 在高并发下报 `database is locked`?**
A: 这是 SQLite 的写锁问题，不是你后端代码的问题。要么切到 MySQL（`DATABASE_URL=mysql+pymysql://...`），要么把并发降到 50 以下——**报告里也可以顺势把这个当成一个可观察到的性能瓶颈来分析**，加分项。
