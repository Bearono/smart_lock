# ARM64 门锁模拟服务

独立服务模拟锁舌状态，使用独立密钥验证命令，持久记录命令 ID、到期时间及观测状态。支持正常、卡住和反馈丢失三种状态。所有结果明确标为 `SIMULATED`，不拥有签发开门授权的能力。

从仓库根目录启动：

```sh
python deploy/init_local_tls.py
python deploy/simulated_lock.py init
docker compose -f compose.lock-sim.yaml up -d --build --wait
python deploy/simulated_lock.py status
```

默认绑定本机 HTTPS 19443。镜像指定 linux/arm64；x86 主机需要 ARM 仿真支持。设备通过 `remote_actuator.py` 连接，使用项目 CA 校验服务证书，独立密钥不与用户密码或设备登记口令共用。

## 可视化面板

服务启动后，在电脑执行：

```sh
python deploy/simulated_lock.py panel
```

浏览器会打开 [门锁面板](https://localhost:19443/panel)，获得仅用于查看的凭据。关闭标签页后可重新运行命令；首次使用需按[部署指南](../../deploy/README.md)核对并信任项目 CA。

录制时将面板切到全屏，在 Web 或 Android 客户端完成正常的验证与开门流程。面板约每秒读取模拟服务的观测状态，展示锁舌变化、最新执行结果和最近八条命令。它没有开门或故障注入按钮，也不持有命令签名密钥。

锁舌动画表示模拟锁状态；系统没有门扇位置传感器，因此不展示门扇已打开的结论。反馈丢失、执行失败和连接中断分别显示。已有记录若缺少执行时间，保留为未知，不推算补写。

## 实现与验证

`service.py` 负责认证与 HTTP，`state.py` 负责持久事务，`viewer.py` 派生独立只读凭据，`static/` 提供无外部依赖的面板。浏览器凭据不授予控制接口权限，状态接口不允许跨域读取。

CI 使用独立新卷验证签名、过期、幂等、故障、面板授权和重启保存；浏览器测试覆盖面板布局及状态变化。不要对已有演示卷运行要求空状态的 `verify_lock_sim.py`。

详细配置与语义见 [设备协议](../../docs/reference/device-protocol.md)。
