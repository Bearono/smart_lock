# 树莓派设备服务

运行真实相机采集、人脸与活体推理、协议会话、命令轮询及设备心跳。

- `app.py`：经过命令认证的设备 HTTP 入口。
- `camera_core.py` / `cv/code`：有界采集、模型校验、模板与推理。
- `transmit.py`：共享协议的设备适配。
- `command_executor.py` / `remote_actuator.py`：指令幂等执行与模拟锁适配。
- `runtime.py` / `gunicorn.conf.py`：每个 worker 的任务生命周期。
- `tests`：模型、相机与模板边界测试，不代表实际硬件性能。

CSI 摄像头采用原生 Picamera2 部署，使用系统兼容依赖。容器镜像为独立 amd64/arm64 验证入口，不把 V4L2 容器结果当作 CSI 实测。未配置执行器时明确返回不可用；模拟执行需要显式配置。

启动、模型准备、模板管理与转发见 [部署手册](../../deploy/README.md)，执行与重放语义见 [设备协议](../../docs/reference/device-protocol.md)。
