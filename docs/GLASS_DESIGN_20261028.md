# 玻璃材质与交互设计 · 2026-10-28

## 参考与取舍

用户要求保留智能家居的温暖感，去除口号和无用说明，并参考 iOS Liquid Glass、Apple Home 与米家的成品体验。

| 官方参考 | 本项目采用的原则 |
| --- | --- |
| [Apple：Meet Liquid Glass](https://developer.apple.com/videos/play/wwdc2025/219/) | 材质、光照和运动统一；触点附近发光，形变有弹性；导航浮于内容之上 |
| [Apple：Materials](https://developer.apple.com/design/human-interface-guidelines/materials) | 玻璃用于导航、工具栏和临时交互，不把表格、图像和全部内容都透明化；避免玻璃叠玻璃 |
| [Apple：交互式自定义玻璃](https://developer.apple.com/documentation/SwiftUI/Applying-Liquid-Glass-to-custom-views) | 控件响应触摸和指针，选中项之间有连续的材料变化 |
| [Apple Home](https://www.apple.com/home-app/) | 设备状态和摄像头内容优先，操作入口集中，状态与动作分离 |
| [米家](https://home.mi.com/index.html?isappinstalled=1)、[官方设备控制说明](https://ics-resources.xiaomi.com/ics-resources/articles/60e424c4f166ecfd410eaf56.html) | 通过设备卡片进入具体控制，按钮和状态采用直白、可识别的名称 |
| [MDN：backdrop-filter](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/backdrop-filter)、[feDisplacementMap](https://developer.mozilla.org/en-US/docs/Web/SVG/Reference/Element/feDisplacementMap) | 使用浏览器对真实背景的滤镜与位移，不用静态高光图片冒充实时背景 |

没有复制 Apple/小米源代码、图标或专有资产。保留既有项目插图及其来源说明，没有引入新的运行依赖。没有增加天气、房间、联动等当前后端不支持的演示功能。

## 实现

- `src/shared/material/optics.js`：根据圆角矩形的有符号距离生成边缘法线，中心保持中性；通过 R/G 通道驱动 SVG 背景位移。法线图只含几何数据，不读取截图、相机图像或个人信息。
- `glass.ts`：统一 `v-glass` 生命周期。背景由浏览器实时合成；几何变化时重新生成法线图，单图最长边不超过 384 像素。指令卸载后移除滤镜、观察器和待执行帧。
- `spring.js`：有阻尼的弹簧积分，按小步长计算并限制长帧跨度，避免 30/60/120 Hz 或短暂卡顿造成不稳定。
- `interaction.ts`：统一鼠标、触屏和键盘按压反馈；压缩后释放有可测过冲，再收敛到原尺寸。触点高光按帧合并，取消、失焦、页面隐藏时复位；静止时没有持续动画循环。
- `selection.ts`：导航共用一个选中底片，位置和大小连续变化，按钮自身布局与点击位置不随底片改变。
- 弹窗保留原生 dialog、焦点回退与键盘行为，入场使用同一弹簧参数生成动画。
- CSS 材质变量集中在 tokens；内容卡片采用高不透明度，摄像头原图不做折射或模糊。透明反向命中层保证按下边缘后，按钮视觉收缩不会把原点击区域缩走。

这是网页端实时合成与物理运动实现，不等同于 Apple 私有原生材质管线；不同浏览器的 SVG 背景滤镜支持、合成效果和性能可能不同。支持不足时退回普通毛玻璃或实色；不承诺所有设备固定帧率。Web 界面也不提供 iPhone 的触觉马达反馈。

## 可读性与无障碍

“减少动态效果”下关闭回弹、移动高光与弹窗运动；系统减少透明度或强制颜色时使用实色。没有为效果关闭身份验证、CSRF 或 CSP。动效不阻塞业务请求，也不负责判断执行成功。

删除侧栏隐私宣言、首页口号、装饰性英文眉题和无交互的家庭卡片。标题采用功能名称，空态说明下一步，离线和硬件限制仍保留。

## 验证和人工验收

新增纯算法检查覆盖多刷新率弹簧的稳定/过冲，以及法线的中心、对称、透明度和内存边界。`npm run test:material` 在隔离浏览器检查实时滤镜、按压与收敛、空闲停止、减少运动、强制颜色、路由资源释放、边缘点击与键盘操作；不登录或写入真实业务数据。完整页面继续由 `test:browser` 检查。

人工查看时请关注：导航选中底片的移动、按钮按下和释放、鼠标在玻璃上移动的光照变化、内容滚动经过顶部栏时的背景变化，以及弹窗的入场与关闭。静态截图无法表示这些交互。

## 第二轮完善：颜色与层级

补充比较 [Home Assistant 的颜色规范](https://contributors.home-assistant.io/design/foundations/color/)、[仪表板布局规范](https://contributors.home-assistant.io/design/dashboards/)、[Apple Home 使用界面](https://support.apple.com/en-euro/guide/iphone/iph22d98bbca/ios) 和 [小米应用商店的官方米家截图](https://m.app.mi.com/details?id=com.xiaomi.smarthome)。重点借鉴颜色的语义分工、设备与操作的关联，以及导航和内容的层级，不照搬其功能或品牌资产。

将大面积灰绿和偏黄背景调整为暖白/石墨灰；灰蓝只用于主动作和选中态，绿色保留给正向设备状态，琥珀/红色表示警告和错误。中性表面、控件边框、辅助填充、玻璃工具栏与环境底色统一使用用途变量。登录仍保留自然木色照片，内容区减少照片着色，避免全页泛黄。

相机卡片合并标题和操作，按钮改为“拍照”，清理重复引导。系统增强对比度时采用实色，同时停止生成折射图；减少动态效果下进度条也停止移动，触屏取消操作不注入额外回弹冲量。补充对主按钮、次要文字及深色背景上玻璃工具栏文字的对比度检查；这属于指定场景的自动验证，不代表完成整个站点的 WCAG 认证。

本轮前端单元测试共 16 项通过，类型检查、ESLint、Prettier 与生产构建通过；隔离浏览器完成 35 项响应式、5 项文字放大及业务断言，材质交互检查扩展为 10 项，包含增强对比度时折射资源的停用与恢复。记录保存在 releases/refinement-* 文件中。测试图里的设备与账户是夹具数据，不能用来证明实机在线；本轮没有新增远程 CI 通过记录。
