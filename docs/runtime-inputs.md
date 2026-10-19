# 运行时输入和冷构建范围

Xcode XIP 含 Xcode 工具、SDK 与开发者框架，不含完整 macOS 用户态。当前成功候选还从以下独立输入恢复了原版 Intel 框架、服务、ICU 数据和系统元数据：

| 输入 | 用途 | 当前限制 |
| --- | --- | --- |
| Xcode 26.6 / 17F113 XIP | 原版工具与 SDK | 原版 xcodebuild SHA256 锁定；没有 CMS 签名链验证 |
| Ubuntu base 24.04.5、Darling v0.1.20260608 | Linux guest 和兼容层基础 | SHA256 固定；仅基础安装 |
| Apple Intel recovery 26.6.2 / 25G83 | 部分 frameworks、原版 daemon、ICU、元数据 | 现有下载脚本用 recovery latest 查询，未来可能换版本；精确冷输入锁定仍待补齐 |
| Apple InstallAssistant 140-93587 / 25G83 | 完整 Intel 共享缓存与框架资源 | 18,384,624,402 字节，URL/包 SHA256 在依赖锁文件；镜像整体 SHA384 差异未解决 |
| 17 个开源源码仓库及补丁 | Darling server、XNU emulation、framework 兼容修复 | 源码基线和补丁字节已固定，restore-sources 可恢复 |
| CocoaPods gems、Swift runtime、其他开源源码 | Pod、Swift、兼容模块构建 | workspace 内分别有锁文件/构建脚本；完整构建顺序仍待整理 |

恢复文件、共享缓存及由它们重建的 Apple 映像均不会进入本工程公开源包。固定版本映像的元数据恢复是当前实现的一部分，不能把任意其他 macOS 版本文件直接替换进来。

当前安装包能够真实完成基础环境和 XIP 导入；`adopt` 能接入已经构建并通过哈希链检查的成功候选。两者之间仍有冷重建缺口：许多历史构建脚本读取此前的运行报告/阶段目录，需要建立完整的有向构建依赖图，移除对手工实验产物和绝对工作区状态的依赖，并在新目录完整验证。在此之前，`setup` 不会宣布已成功复制 iOS 编译里程碑。

`config/runtime-recipe.json` 给出每阶段已有入口、输入和具体缺口。列表中晚期的 server/FSEvents/vchroot/metadata 修复不能单独完成整个环境，直接依次运行那几个晚期脚本并不足够。开发入口用于继续逐模块整理、构建和测试；不是用一个很长的 shell 命令掩盖缺少前置产物。

里程碑验收目前是原版 xcodebuild 对本地 CocoaPod 实际 C/Objective-C 编译、静态库和 iPhoneOS/arm64 App 链接；关闭签名，未在设备运行。资源编译、Unity/UE 导出工程、完整严格 CoreServices 策略、归档、导出、有效证书签名及设备信任仍未完成。成功日志不应自动推导为这些功能可用。
