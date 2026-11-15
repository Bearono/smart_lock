# 可选音频实验入口

Windows 入口为本目录的 `Start-CourseAudio.cmd`，调用仓库内现有 `deploy/audio_console.py`；其前提是已安装本机课程 Python 环境。命令行跨平台入口：

```sh
python deploy/audio_console.py --help
python deploy/audio_peer.py --help
```

这些工具不参与门锁、手机主界面和 ARM 执行流程。当前交付不再要求音频实测。
