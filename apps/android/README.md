# Android 客户端

安居 SmartLock 通过受限 WebView 加载门锁服务。原生层负责 HTTPS 校验、连接设置和错误恢复；业务后端负责认证与授权。应用只申请网络权限，拍照由树莓派摄像头完成。

## 下载

**[下载 SmartLock 1.1.0 APK](https://github.com/Bearono/smart_lock/releases/download/v1.1.0/SmartLock-1.1.0.apk)** · [Release 与 SHA-256 校验文件](https://github.com/Bearono/smart_lock/releases/tag/v1.1.0)

| 属性     | 当前安装包                       |
| -------- | -------------------------------- |
| 系统要求 | Android 8.0 / API 26 及以上      |
| 应用 ID  | `org.smartlock.course`           |
| 版本     | `1.1.0`，versionCode `2`         |
| 签名类型 | 调试签名，供本地联调使用         |
| 默认地址 | `https://localhost:8443`         |
| 附加信任 | 项目 CA 公钥证书，仅作用于本应用 |

GitHub Release 中的 APK 与已安装到测试手机的版本一致。CA 证书不包含私钥；服务地址在首次启动时使用，后续优先读取本机保存的地址。CI 的 `smartlock-android-debug` 构建产物使用通用配置，不包含本机 CA 与预设服务地址。

## 连接后台

先完成[后台与设备部署](../../deploy/README.md)。使用发布包连接原联调环境时，解锁手机、开启 USB 调试并连接电脑，然后执行：

```sh
adb reverse tcp:8443 tcp:8443
adb install -r SmartLock-1.1.0.apk
```

打开应用，确认服务地址为 `https://localhost:8443`。拔线、设备重启或 ADB 服务重启后，需要重新建立端口转发。APK 本身不承载 API、数据库、人脸模型或门锁执行服务。

连接其他部署时，填写手机可访问、与服务证书主机名一致的 HTTPS 地址。参考 Compose 只监听回环地址；无线访问需先配置局域网 HTTPS 入口。使用不同的私有 CA 时，按下节重新构建匹配证书的 APK；公开受信证书使用系统信任链。

## 从源码构建

要求 JDK 17+、Android SDK Platform 36、Build Tools 36.0.0。以下命令从仓库根目录执行，路径参数替换为本机安装位置：

```sh
python apps/android/test_jvm.py --jdk /path/to/jdk
python apps/android/build_sdk.py --jdk /path/to/jdk --sdk /path/to/android-sdk
```

为私有 CA 部署构建客户端：

```sh
python apps/android/build_sdk.py --jdk /path/to/jdk --sdk /path/to/android-sdk --ca-cert deploy/tls/ca.crt --endpoint https://localhost:8443
```

构建输出位于 `apps/android/app/build/outputs/apk/debug/`，包括 APK 和 `build-evidence.json`。脚本校验对齐与签名，记录源码、证书和 APK 的 SHA-256。升级已安装应用需要使用相同签名；重新生成签名密钥会失去覆盖安装兼容性。调试包不用于应用商店生产发布。

## 行为约定

- 切换身份验证器、进入连接设置再返回时保留正在进行的页面流程；会话有效期由服务端控制。
- 更换服务地址或主动清除登录状态会清除本机网页会话；密码和验证码不保存到原生配置。
- 断网、TLS 错误、HTTP 错误、加载超时和网页进程退出均提供恢复入口；重连不重发门锁命令。
- 拒绝明文、混合内容、外部来源跳转、网页摄像头/麦克风授权及文件访问；不提供 JavaScript 原生桥。

实现依据：[WebViewClient](https://developer.android.com/reference/android/webkit/WebViewClient)、[网络安全配置](https://developer.android.com/privacy-and-security/security-config)。
