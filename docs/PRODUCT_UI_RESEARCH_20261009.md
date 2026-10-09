# 成品界面再调研与落地记录

调研日期：2026-10-09。目标：树莓派 4B / 2GB 门锁与摄像头课程项目。本轮同时检索门锁应用、门铃摄像头应用与家庭控制台，优先使用官方产品页、帮助中心及用户手册。以下“借鉴”是设计判断，并非这些产品对本项目的背书。

## 比较矩阵

| 成品及一手资料 | 可核实的设计与交互 | 本项目采用 | 暂不采用 |
| --- | --- | --- | --- |
| [Nuki 权限管理](https://help.nuki.io/hc/en-001/articles/360017195078-How-can-I-add-edit-or-delete-lock-permissions) | 用户权限独立管理；门锁相关资料突出当前锁状态与操作 | 单独的锁状态焦点；权限放在管理员入口 | 不把解锁和拉开锁舌混为一项，本项目没有独立开锁舌驱动 |
| [Yale Home App Guide](https://www.yalehome.com/au/en/documents/technical-downloads/smart-locks/yale-home/yale-home-app-guide.pdf) | Owner / Guest 权限不同，支持访问时段；访客不等于管理员 | 访客与成员管理分开；关键操作明确身份 | 不宣称已拥有 Yale 全部定时规则或门磁能力 |
| [Ring 控制设备](https://ring.com/support/articles/gh3fn/controlling-your-devices-in-the-app) | 首页区分摄像头预览与其他设备，连接异常有状态提示 | 画面与门锁控制相邻但分区；离线提示贴近控制 | 不显示未经设备上报的电量、画面或在线状态 |
| [Eufy 新版应用说明](https://service.eufy.com/article-description/Introduction-to-New-eufy-App) | Home 与 Events 分工，事件按日期、设备和类型筛选 | 首页最近动态，完整记录有设备筛选 | 不把说明页中的未来功能计划当作已经交付的能力 |
| [Arlo Dashboard](https://www.arlo.com/en_gb/support/faq/arlo-app-and-automations/what-is-the-dashboard-on-my-arlo-secure-app-and-how-does-it-work) | 仪表盘强调常用控件，Feed 承载事件 | 家庭概览与动态分开；首页只放少量最近记录 | 不加入可拖拽大屏配置器，避免单门锁项目失焦 |
| [Apple Home](https://www.apple.com/home-app/) | 家庭、房间和设备组织，摄像头与常用设备可直接访问 | 清晰设备上下文、减少首页解释性大段文字 | 不引入没有接口支持的场景与家庭自动化按钮 |
| [Google Home 使用说明](https://support.google.com/googlehome/answer/7071794?hl=en-NZ) / [应用更新](https://store.google.com/magazine/google-home-app-updates?hl=en-US) | 常用设备与活动有明确入口，跨设备体验 | 手机保留四个主要入口，桌面采用侧栏 | 不复制生态联动、云录像或订阅能力 |
| [Aqara Panel Hub S1 Plus](https://www.aqara.com/eu/product/panel-hub-s1-plus-desktop-version/) | 家庭面板强调设备卡片、图标及可识别名称 | 设备显示名称与状态并列；温和而清楚的控件 | 这是硬件面板参考，不当作同一款手机应用 |
| [Tapo 摄像头分享](https://www.tp-link.com/ph/support/faq/2710/) | 以家庭成员访问为核心组织设备使用 | 保留按账户、按设备授权，敏感媒体依权限访问 | 不加入未支持的摄像头云分享链接 |
| [Reolink 沉浸预览](https://support.reolink.com/articles/360035359813-How-to-Use-the-Immersive-Preview-Mode-on-Reolink-App/) | 预览减少外围干扰；详细控制进入独立页面 | 16:9 画面、轻量标题与放大入口 | 当前只是快照，不加播放按钮伪装直播 |
| [SmartThings 使用应用](https://support.smartthings.com/hc/en-us/articles/360051930512-Using-the-SmartThings-App) | 家庭设备与常用操作有组织地呈现 | 主导航保持稳定；设置与日常控制分层 | 不复制全屋设备目录与规则引擎 |
| [SwitchBot Lock 家庭分享](https://support.switch-bot.com/hc/en-us/articles/6346053655831-How-to-Share-SwitchBot-Lock-with-Your-Family) | 家庭共享是门锁的重要场景 | 独立成员与访客凭证 | 文档涉及共享账户的做法不采用，本项目保留独立身份和审计 |
| [Homey Dashboards](https://homey.app/en-us/features/dashboards/) / [官方操作帮助](https://support.homey.app/hc/en-us/articles/16732145289116-Create-and-manage-Homey-Dashboards) | 卡片可组合，手机和平板显示不同列数 | 同一业务组件适应桌面和手机，而非整页缩小 | 不为课程项目加入股票、天气等无关占位控件 |
| [Home Assistant Cards](https://www.home-assistant.io/dashboards/cards/) | 状态、控制、历史、摄像头卡片职责明确，可条件显示 | 将导航、家门、认证、动态和共享组件拆分 | 不复制复杂配置编辑器；UI 隐藏不能替代服务端权限 |
| [UniFi Protect 7.0](https://blog.ui.com/article/introducing-protect-7-0) / [Access 与 Protect 门监控](https://help.ui.com/hc/en-us/articles/18781917574423-Pairing-UniFi-Access-and-Protect-Devices-for-Door-Monitoring) | 摄像头布局与门禁事件结合，真实画面和解锁事件关联 | 同设备的画面、状态、操作审计保持一致上下文 | 不声称已有录像回放、多路直播和企业级门禁部署 |

阅读范围说明：官方资料可确认信息架构与功能分工；产品页的图片索引和可访问图像用于外观参考。Yale PDF 的文字已读，但截图接口因重定向失败，不能称为完整逐页视觉检查；Ring 部分 GIF 预览也未能解析。没有登录这些厂商的真实设备账户，也没有复制品牌截图到项目中。

## 为什么上一版显得不够成熟

上一版暖色铺得过满，大插画与问候语占据核心空间，卡片层级相似；桌面沿用手机导航，视觉重点没有落在真实设备上。仅调色无法解决这些问题。

本轮选择暖白、浅灰绿和深鼠尾草绿：让原木与自然光承担登录页的温度，业务页面保持白色卡片与克制边界。状态用文字、图标和颜色共同表达，不靠绿色暗示整个系统安全。未知锁状态使用中性色。

## 已落地的界面结构

1. 登录页：原创住宅门厅背景与简洁的两步登录表单；移动端缩小装饰区域。该背景只用于品牌装饰，绝不作为摄像头画面。
2. 桌面：固定侧栏承载我的家、动态、访客、设置；管理员入口单独列出。顶栏只保留页面上下文与账户。
3. 手机：四项底部导航，页面内容自然纵向排列；保持键盘焦点、文字放大及小屏适配。
4. 我的家：紧凑欢迎区，明确设备选择；左侧画面与上报信息，右侧锁状态和身份验证入口；下方最近操作记录。
5. 快照：空白、加载、失败、放大都使用真实状态；明确接收时间不等于拍摄时间，不宣称实时视频。
6. 动态：当前设备最近四条操作审计；“查看全部”带入设备筛选。命令提交与执行确认仍分开表达。
7. 控制：设备离线时禁用控制；在线但传感器状态未知时允许明确上锁。提交后继续使用原有确认、超时、恢复流程。

## 工程结构与验证边界

设计令牌位于 `tokens.css`，外壳、首页、认证样式分别位于 `shell.css`、`home.css`、`auth.css`。最近动态是独立业务组件，通过现有 API 与资源加载器获取数据。后端历史查询增加设备过滤和访问校验，没有在前端拼造设备记录。

验证包含类型检查、格式、静态检查、前后端测试、浏览器交互、35 个响应式检查和 5 个文字放大检查。桌面与手机截图使用隔离测试数据，不能证明物理锁执行或 Pi 摄像头能力。完整功能边界见 `FUNCTIONAL_COMPLETENESS_AUDIT.md`。

后续界面评估应基于真实设备截图、上报延迟与使用反馈，优先看任务完成率、误操作和异常理解，避免只追求效果图。
