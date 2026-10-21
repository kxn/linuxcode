# Storyboard 编译触发的服务与原始资源目录

当前原始命令是 `xcodebuild … -sdk iphoneos -destination generic/platform=iOS ARCHS=arm64 build`，没有 test 动作。完整构建日志中触发 CoreSimulator 的是 Unity 启动页的 CompileStoryboard → 原版 ibtool。当前尚未观察到启动模拟器设备、安装/运行用户 App 或执行 XCTest。CoreSimulatorService、simdiskimaged 和 SimulatorTrampoline 是 macOS 宿主侧组件，不等同于 iOS 模拟器内部的系统进程。服务查询也不等于已经启动模拟器。

实际观察到的链路是：xcodebuild → ibtool/ibtoold → CoreSimulatorService → simdiskimaged 与 SimulatorTrampoline。磁盘服务尝试枚举已挂载映像，因此牵涉 DiskImages2、IOKit 和 DiskArbitration。这里只记录已观察行为；没有据此认定所有模拟器、挂载、驱动和图形 API 都必须完整实现。

已确认两个不同的 Trampoline 故障：cfg136 未给它加载器作用域，加载旧 Darling AppKit 后在 XCloseIM(NULL) 崩溃。cfg137 添加它的真实路径后，确实加载了原版 AppKit，越过 X11 崩溃；新的故障位于原版 NSApplication 默认菜单初始化中的 Swift class metadata 布局，字段布局指针为0x40，尚未修复。创建 NSApplication/NSMenu 等内存对象，不代表出现窗口。

磁盘服务的第一个异常已在 objc_exception_throw 入口捕获：NSInvalidArgumentException，NSPlaceholderString initWithFormat:locale:arguments: 收到 nil。独立探针确认框架资源内容可读取，但原版 DIError.frameworkBundle 固定使用 `/System/Library/PrivateFrameworks/DiskImages2.framework`，该规范位置在旧候选中不存在。新的隔离stage将已通过代码/绑定检查的完整框架放到原始规范路径；原始可执行字节不变。相同探针由抛异常变为0、1、100、152、153、157、-1共七个错误描述全部成功。包括实际调用路径中的错误153。先前直接从裸提取目录加载的探针也保留，但它缺少bundle元数据，不能代替框架布局对照。

这只修复了错误描述构造。DiskImages2 寻找磁盘映像 IO controller 的失败仍需处理；异常展开器读取 Swift async 标记帧指针的问题仍未修复。源码参考 libunwind checkout 没有编译、修改或选入候选。不能把字符串探针通过当成原版磁盘服务或 Storyboard 已成功。

```bash
python3 scripts/stage-canonical-resource-framework.py \
  --parent-stage artifacts/private-procfs-auditsession21-stage.json \
  --framework runtime/resource-framework-overlay-coresim-diskmanagement-v1/frameworks/DiskImages2.framework \
  --canonical /System/Library/PrivateFrameworks/DiskImages2.framework \
  --inspection artifacts/coresim-diskimages2-resource-v3-independent-inspection-v2.json --tag 自己的新标签
python3 scripts/probe-diskimages-error-localization.py --configuration config/direct-resource-tool-environment-v137.json --stage artifacts/新stage.json
python3 scripts/probe-original-storyboard.py --configuration config/direct-resource-tool-environment-v137.json --stage artifacts/新stage.json --with-disk-services --diagnostic-disable-volume-manager --trace-job-state
```

最后一条里的原版 EnableVolumeManager NO 仍只用于诊断，不能当作默认启动问题的修复。原生会话与原生 Apple 链接须串行。此增量依赖先前研究附件与用户自行提供的 Apple 输入；默认安装候选没有提升，冷重建仍未完整打通。reference 只保存UTF-8源码、报告、日志、路径和摘要，不含 Apple/Unity 二进制、SDK、XIP、core、证书或私钥。
