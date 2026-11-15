# 设备资源与课程实机采证

`deploy/device_acceptance.py` 是仅依赖 Python 标准库的有限时长采证工具。它不打开摄像头、不运行人脸识别、不控制锁具、不重启服务、不制造断网，也不读取运行口令、数据库、模板或照片。当前 CSI 相机不可用时，仍可采集 Pi 的资源和软件就绪证据，但不能据此标记相机、人脸或物理开门验收完成。

## 在 Pi 上采样

在项目根目录以设备服务用户运行；输出文件必须不存在：

```sh
.venv-pi/bin/python deploy/device_acceptance.py --device-id pi_csi_01 --seconds 300 --interval 5 --output instance/evidence/resources-01.json
```

默认记录的是采证工具自己的 RSS。要观察设备服务，先用 `systemctl --user show smart-lock-device.service --property MainPID --value` 查看主进程 PID，再以 `--pid PID` 明确指定。Gunicorn 主进程与 worker 是不同进程；分析推理内存时应选择实际 worker PID，本工具不把某一进程 RSS 当成整棵进程树。进程退出后保留 `unavailable`，不会自动改为观察其他进程。

可选只读软件就绪检查：

```sh
.venv-pi/bin/python deploy/device_acceptance.py --device-id pi_csi_01 --seconds 300 --interval 5 --health-url https://localhost:5443/health/ready --ca-file deploy/tls/ca.crt --http-timeout 5 --output instance/evidence/readiness-01.json
```

CA 路径应指向该安装信任的**公有 CA 证书**。工具不跳过 TLS 校验、不跟随重定向、不使用代理环境变量或登录凭据，不读取响应正文。HTTP 仅允许字面回环 IP（如 `http://127.0.0.1:5000/health/ready`），其他地址必须使用 HTTPS；URL 禁止用户名、口令、查询参数和片段。就绪 200 只表示该接口返回成功，不表示摄像头在线。

时长允许 1～7200 秒，间隔 0.1～60 秒，单次 HTTP 超时 0.1～30 秒。采样和网络耗时计入实际时长，因此慢请求可能使采样间隔与结束时间晚于目标。Ctrl+C 保留已采样结果并标记未完成。脚本只在当前终端运行，不安装后台任务。

## 报告的含义

- 环境：UTC 起止时间、操作系统、Python、CPU 数量和机器架构；`device_id` 是维护者指定的标签，不是经过硬件认证的身份。
- 资源：`/proc/stat` 总 CPU 计数及两次采样间使用率，`/proc/meminfo` 可用/使用内存，指定 PID 的 RSS，以及 `/sys/class/thermal` 的温度。首次 CPU 采样无使用率；计数倒退也不会伪造数值。
- 缺项：Windows 或缺失权限/文件时明确记录 `unavailable`；不以零填补缺失读数。不存在通用硬件温度阈值，工具不擅自给出热稳定性合格结论。
- 网络：逐次 HTTP 状态、耗时与有限错误类别。失败采样全部保留；不写入服务响应正文和可能包含凭据的异常原文。
- 源码：Git HEAD（可获得时）与设备 Python 源码、共享协议及指定采证/部署脚本的逐文件 SHA-256。工作区修改由实际文件哈希体现，不能只用 HEAD 代表未提交源码；不包含模型、依赖、前后端完整源码及个人材料。结束时再次记录摘要，`source_unchanged=false` 表示试验期间源码发生变化。

输出 `completed=true` 仅表示采样完成。退出码 0 表示采样完成、源码摘要稳定、可选 HTTP 检查没有失败；即使退出码为 0，也应检查资源缺项。退出码 1 表示中断、源码变化或 HTTP 失败，2 表示参数/文件错误。报告固定标注硬件功能及生物识别准确率 `not_tested`，没有整体“硬件通过”字段。

## 配套课程算法试验

在同一 Pi、同一源码版本上独立运行已有工具；采证工具不替代或自动触发这些实验：

```sh
PYTHONPATH=packages/smartlock_protocol .venv-pi/bin/python -m smartlock_protocol.course_lab --output instance/evidence/course-crypto-01.json
PYTHONPATH=packages/smartlock_protocol .venv-pi/bin/python deploy/course_benchmark.py --iterations 50 --output instance/evidence/course-cpu-01.json
PYTHONPATH=packages/smartlock_protocol .venv-pi/bin/python deploy/protocol_benchmark.py --iterations 50 --output instance/evidence/protocol-cpu-01.json
```

每次使用新文件名；现有 `protocol_benchmark.py` 会覆盖同名输出。算法报告包含 XXTEA/RSA、签名/DH、分发或协议的功能/CPU 测量，不能当成网络、人脸或开锁时延。Windows 执行所得架构与数据仍然是 Windows 证据。不要将 Python XXTEA 与原生 AES-GCM 的耗时直接当作同语言算法优劣排名。

后续恢复 CSI 后，应另测采集、识别/PAD、上传和认证全链路。真实音频传输需麦克风/扬声器及独立试次；物理声学指纹还需注册、匹配和跨设备负样本。资源采证不补足这些硬件条件。现有协议和执行限制见 [设备执行说明](DEVICE_EXECUTION.md)，密码实验口径见 [课程密码实验](COURSE_CRYPTO_LAB.md)。
