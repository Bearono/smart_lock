# Windows 与树莓派密码算法实验

当前用户指定只推进 Windows 软件及 Pi 4B/2GB 摄像头联调，最新排除 Android 与实体锁；音频软件已接入，详见 [防伪与音频验收](PAD_AUDIO_ACCEPTANCE.md)。本页只描述已新增的可运行代码，不代表教学大纲全部验收完成。

## 运行

在项目 PowerShell 中使用已经安装依赖的虚拟环境：

```powershell
$env:PYTHONPATH = "$PWD\packages\smartlock_protocol"
& .\.venv-test\Scripts\python.exe -m smartlock_protocol.course_lab --output releases/course-crypto-windows.json
```

树莓派在 `/home/taylor/smart-lock` 中执行：

```sh
PYTHONPATH=packages/smartlock_protocol .venv-pi/bin/python -m smartlock_protocol.course_lab --output instance/course-crypto-pi.json
```

输出文件已存在时拒绝覆盖，请为新试次更换文件名。报告只包含环境、检查结果与单次总耗时，不保存密钥、共享秘密、照片或模板。单次总耗时包含密钥生成，不能当成算法吞吐量或安全性排名。

## 实现和边界

| 算法 | 当前代码检查 | 使用边界 |
| --- | --- | --- |
| XXTEA | 显式 uint32 输入，128 位密钥；独立 C 实现生成的固定向量；不同长度往返和非法输入拒绝 | 教学实验，未提供完整性认证，不能直接代替线上 AEAD |
| RSA | 2048 位密钥、OAEP/MGF1 SHA-256、固定用途标签；密钥封装往返，错误密钥和截断密文拒绝 | 单次密钥封装实验；未构成完整 KDC、身份管理或端到端分发系统 |
| ECDSA | P-256/SHA-256；签名验签，篡改、其他签名者和无效 DER 拒绝 | 独立签名实验；未建立证书信任与吊销体系 |
| DH | X25519/HKDF SHA-256；两端一致、上下文隔离、低阶全零公钥拒绝 | 演示共享密钥；没有对端身份认证，不能宣称抵抗中间人攻击 |

线上设备命令继续使用现有双向确认 SPAKE2、HKDF 和 AES-GCM。本实验模块不会被设备执行器导入，也不创建电脑自启或自动重连任务。

XXTEA 轮次及混合运算参考 [xxtea-c 原始实现](https://github.com/xxtea/xxtea-c/blob/master/xxtea.c)，使用字数组接口，未使用该库的字符串密钥归一化和字节填充格式。RSA、ECDSA、X25519 使用 [cryptography 官方接口](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/)。

## 密钥分发对照代码

`smartlock_protocol.distribution_lab` 提供两种隔离实验：

- KDC：维护者授权发行，使用各接收方独立预置的 AES-256 长期密钥保护会话票据；双方取得相同随机会话密钥。票据绑定双方身份、会话编号和有效期。
- 公钥分发：RSA-2048 OAEP 封装随机会话密钥，预置信任的发行者使用 ECDSA-P256 签署身份、会话、有效期和密文；接收方先验签再解封装。

两种接收路径都校验身份、会话、有效期和重放。实验重放表只在内存中保存，上限 2048，不自动淘汰；生产所需持久化、并发仲裁、证书注册和吊销不由本实验提供。发行由本地维护者调用，不提供未经鉴权的网络发行接口。两种方案均不提供前向保密。KDC 掌握会话密钥；公钥方案依赖可信公钥预置。线上现有 v3 协议的独立持久化和并发测试不应与这些实验混为一谈。

```powershell
& .\.venv-test\Scripts\python.exe -m smartlock_protocol.distribution_lab --output releases/distribution-windows.json
& .\.venv-test\Scripts\python.exe deploy/course_benchmark.py --iterations 50 --output releases/course-benchmark-windows.json
```

树莓派使用同一源码和对应虚拟环境执行，输出到 `instance/`。算法 CPU 实验包含加解密、签名验签、DH/HKDF、KDC 发行和双方解票、公钥分发，记录样本数、中位数和 p95；RSA 密钥生成单列、最多 10 次。初始化后先预热，不把密钥生成混入每次加解密耗时。Python XXTEA 和原生 AES-GCM 的时间不能作为同语言算法排名，也不能由速度推断安全性。设备实际 v3 信封测量另由 `deploy/protocol_benchmark.py` 提供。

音频和 Android 按当前用户安排暂缓，完整课程验收不得把它们标成已完成。实体门锁未配备，实机执行应继续返回执行器不可用，锁状态 UNKNOWN。
