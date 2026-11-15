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

`service.py` 负责认证与 HTTP，`state.py` 负责持久事务和状态。CI 使用独立新卷验证签名、过期、幂等、故障和重启保存；不要对已有演示卷运行要求空状态的 `verify_lock_sim.py`。

详细配置与语义见 [设备协议](../../docs/reference/device-protocol.md)。
