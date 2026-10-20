# EventKit 通知与 Swift QuartzCore 帧率 ABI

纯 Linux x86_64 / Darling、无界面。配置 v115、graphics v159，沿用 eventkit overlay。原版 Xcode 工具、Unity/CocoaPods 工程与 CI 命令保留。

恢复 EventKit、CalendarDaemon 和原版 libswiftQuartzCore 三个映像。独立核验 2286 个 GOT 单元和 6750 个绑定，原版可执行字节保持一致。三个原版格式正例、六个损坏对照和实际代码/绑定篡改检查通过；不代表全部框架 API 兼容。

## 通知常量的实际读取

原版 EKEventStoreChangedNotification 的字符串值、31 字节长度和原始对象已核实。经真实 CoreFoundation API 验证其类型 ID 7、UTF-8 值、实际提供者和默认命名空间的指针身份；旧配置缺失、错误值对照均被拒绝。

这项数据测试显式使用 RTLD_LAZY。严格 RTLD_NOW 失败记录保留：它在读取常量之前遇到 LanguageModeling 的 openat_authenticated_np 缺失。新参数只控制研究探针的 dlopen 策略，默认仍为 RTLD_NOW；未修改原版资源工具、项目、CI、导入审计或原有失败状态。数据读取通过不等于上述文件 API 已实现。

## 原版 Swift 构造函数

原版 DTGanache 所需的 CAFrameRateRange.init(minimum:maximum:preferred:) 位于原版 Swift QuartzCore overlay。原版 Swift 编译器生成并链接真实测试程序；对象文件核验仍导入同一个构造符号，运行时核验函数的实际原版提供者。23 项检查覆盖 minimum/maximum、可选 preferred、nil、零、负零、NaN、无穷值及 getter/setter。旧配置重现同一个构造符号缺失，错误最大值期望返回 15。没有另写替代构造算法或猜测 Swift Optional<Float> ABI。

## 当前完整工程

完整 Unity/CocoaPods workspace 的五 target 依赖图和 UTI 预检通过，原版 xcodebuild 实际返回 65。当前阻塞为 __class_setCustomDeallocInitiation。CompileC 为零，最终 App/UnityFramework/AFNetworking 二进制不存在。实际资源编译、完整 Unity/UE 链接、签名及 archive/export 尚未完成，默认安装候选未提升。严格立即绑定、原版 JavaScriptCore 上下文和脚本存储永久冻结仍有未验证项。

## 开发者复现

需要完整 Linux 开发工作区、自行提供的锁定 Xcode/SDK、Intel cache/提取件及 Darling/LLVM。XIP 不含所有系统框架。附件只含源码、配置、文本证据和历史，不含 Apple/Unity 二进制、SDK、XIP、证书或私钥。payload 相对工作区；合并历史时保留已有 revisions。summary 不能作为运行输入。

所有原生运行串行执行，清除 DISPLAY/WAYLAND_DISPLAY/XAUTHORITY，并使用新报告、tag 和 DerivedData。完整工程参数为 unity-ios-cocoapods-v71-probe-arguments.json。研究比较使用本检查点固定的基线报告；新环境应重新生成对应基线。

```bash
python3 scripts/probe-original-framework-cfstring.py --configuration config/direct-resource-tool-environment-v115.json --baseline-probe runtime/direct-resource-tools-5itb62rx/result.json --contract artifacts/eventkit-eventstore-notification-native-contract-v1.json --stage artifacts/private-procfs-v11-stage.json --binding-mode lazy
python3 scripts/probe-original-swift-quartzcore.py --configuration config/direct-resource-tool-environment-v115.json --baseline-probe runtime/direct-resource-tools-9sasbwxh/result.json --stage artifacts/private-procfs-v11-stage.json
python3 scripts/probe-direct-resource-tools.py --configuration config/direct-resource-tool-environment-v115.json --stage artifacts/private-procfs-v11-stage.json
```

前两项应通过，最后一项仍失败。reference/original-file-map.json 记录原始路径和 SHA；日志和历史源码采用 UTF-8 JSON text 封装。
