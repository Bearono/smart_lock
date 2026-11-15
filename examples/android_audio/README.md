# Android 音频实验档案

保留纯 Java 编解码、录音长度约束和密钥交换实现，以及历史测试。这些源码不位于 `apps/android/app/src/main`，不会编入门锁 APK。没有麦克风入口或 Android 应用清单。

需要 JDK 17+，以及与 Android JVM 测试相同的固定 JUnit/Hamcrest 依赖。从仓库根目录执行：

```sh
python examples/android_audio/test_jvm.py --jdk <JDK>
python examples/android_audio/tests/test_codec_interop.py --java <JDK>/bin/java
```

互操作测试使用共享包的可选 NumPy 依赖。源码与合成信道测试保留在独立 CI 任务中，不代表声学实测通过。课程交付已经明确取消音频要求。
