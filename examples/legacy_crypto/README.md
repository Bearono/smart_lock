# 不安全的历史加密示例

这些文件来自旧版课程代码，保留用于理解演进。部分示例使用固定 CBC IV、非密码随机数或缺少消息认证，禁止用于真实密码、相机画面、设备凭据或开门授权。

后端和设备运行目录不再导入这些文件；旧式上传解密器永久拒绝该格式。课程对照请使用 packages/smartlock_protocol 中的受控实验，并阅读 docs/COURSE_CRYPTO_LAB.md 中的边界。

历史 gateway 文件仅保留来源，不保证其脱离旧目录后仍可执行。

vendor_snapshot 保留两份旧 SPAKE2 0.9 源码快照，仅供追溯。它们已移出 Python 运行搜索路径，避免遮蔽 requirements 中固定安装、接受漏洞检查的正式依赖；此举不表示 SPAKE2 本身属于不安全的 CBC 示例。
