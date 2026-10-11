# Windows 与树莓派密码算法实验

当前用户指定只推进 Windows 软件及 Pi 4B/2GB 摄像头联调，Android、音频和新增硬件暂缓。本页只描述已新增的可运行代码，不代表教学大纲全部验收完成。

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

课程任务书中的架构分析、KDC 与公钥分发比较、完整协议安全评估及性能实验仍需分别验收；音频和 Android 按当前用户安排暂缓，不能因这些原语测试通过就标成全部完成。实体门锁未配备，实机执行应继续返回执行器不可用，锁状态 UNKNOWN。
