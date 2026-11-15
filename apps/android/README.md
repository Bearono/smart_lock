# Android 客户端

“安居 SmartLock”使用与网页相同的登录、人脸验证、动态验证码和门锁执行流程。原生外层负责连接设置、HTTPS 校验、加载状态与错误恢复；网页负责业务和权限判断。拍照使用树莓派摄像头，APK 只请求网络权限。

音频实现和测试已迁入 [独立实验目录](../../examples/android_audio/README.md)，不编入门锁 APK。主应用仅包含门锁页面和 HTTPS 来源策略。

## 构建与安装

可使用 Android Studio/Gradle，也可使用官方 SDK 命令行工具，无需安装 Android Studio。命令行方式要求 JDK 17+、Android SDK Platform 36、Build Tools 36.0.0：

```powershell
python apps/android/build_sdk.py --jdk "你的 JDK 路径" --sdk "你的 SDK 路径"
python apps/android/test_jvm.py --jdk "你的 JDK 路径"
```

APK 与构建哈希位于 `app/build/outputs/apk/debug/`。这是课程调试签名包；公开分发需另行配置正式签名。

本机课程联调可以仅向此调试 APK 加入项目的**公开 CA 证书**，不修改手机系统信任、不打包私钥：

```powershell
python apps/android/build_sdk.py --jdk "你的 JDK 路径" --ca-cert deploy/tls/ca.crt --endpoint https://localhost:8443
adb reverse tcp:8443 tcp:8443
adb install -r apps/android/app/build/outputs/apk/debug/app-debug.apk
```

此处 `localhost` 依赖 USB 调试转发；拔掉 USB 或重启 ADB 后需要重新连接并建立转发。无线使用时填写手机可达、与服务证书匹配的 HTTPS 地址。默认地址只在首次启动、尚未保存地址时生效。

## 行为与验收

- 自动打开已保存的服务；进入连接设置再返回不丢失正在进行的验证。切到身份验证器再回来保留页面。账号会话有效期由服务端控制。
- 更换服务地址、主动清除本机登录状态会清除本机网页会话。普通重连与 Activity 销毁不主动删除登录 Cookie；密码和验证码不保存到原生配置。
- 无网络、证书错误、HTTP 错误、加载超时和网页进程退出都有明确提示。重连只访问首页 GET，不自动重新发送开门指令。
- 拒绝明文、混合内容、外部站点、网页摄像头/麦克风授权及文件访问。无 JavaScript 原生桥。截图保护保留。
- 真机验收应覆盖：连接/断线重连、切换身份验证器、拍照和图片预览、人脸 + 动态验证码开锁、回执、上锁与记录。

实现遵循 Android 官方的 [WebView 错误与进程处理](https://developer.android.com/reference/android/webkit/WebViewClient) 和 [网络安全配置](https://developer.android.com/privacy-and-security/security-config)。
