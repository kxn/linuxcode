# SIMD 常量与原版 AppKit 单例元数据

纯 Linux x86_64 / Darling、无界面的实验检查点。原版 Xcode 工具和 Unity/CocoaPods workspace 的 CI 命令保持原样。当前配置为 direct-resource-tool-environment-v88.json，graphics v136、AppKit closure overlay，资源 libSystem 使用 resource-double4-matrix-v1。

本轮真实原生测试确认 matrix_identity_double4x4 的 128 字节与原版 Intel libsystem_m 一致，符合当前 SDK 的 16 字节对齐和列布局。旧配置复现缺失符号；新配置通过 60 项检查，包括原版常量字节、double3x3 回归、重导出指针身份、实际提供者路径和矩阵运算。新增模块只公开 double4x4，libSystem 原有 121 个导出 trie 项和可执行字节保持一致，沿用完整的 20 源码单元实现。常量源码也加入 Darling libm 的 CMake 源列表；本轮没有重新构建整个 Darling。

## 原版 AppKit 与依赖

选入原版 AppKit，以及其九项缺失强依赖：CollectionViewCore、XCTTargetBootstrap、FrontBoard、WindowManagement、CoreAutoLayout、FocusEngine、UpdateCycle、TextInput、UIUtilities。十份映像合计独立核验 8733 个 GOT 单元、129901 个绑定，原版可执行节字节保持一致；原版 dyld_info 的十个格式正例及二十个损坏对照均通过。WindowManagement 的首次 GOT 重建失败后，经 37 项精确导入核验才建立第二候选，失败记录保留。

AppKit 的首次恢复暴露了两类真实数据：lround 的原版跳转桩/GOT 身份，以及不在 objc_classlist 中的 Swift 单例类。lround 经原版缓存 patch 记录、GOT 单元及 libSystem 到 libm 的重导出链核对，不按折叠后的相同函数地址猜名字。另外两个未识别指针来自 TrustedUIServiceProxy 的共享缓存方法/协议列表，随后由真实的单例类元数据恢复处理；没有把它们绑定到猜测的导出，也没有关闭未知跳转桩检查。

Swift ABI 的 TargetSingletonMetadataInitialization 对无 resilient ancestry 的类存储 IncompleteMetadata，对另一类存储 ResilientPattern。新增检查器验证前一种布局的 descriptor 身份、Swift 类标志、元类和双方 ro-data。核验覆盖 AppKit 中 32 个单例类及其元类，共 64 个对象。其中 28 个类原已由 objc_classlist 路径覆盖，新增恢复的是其余 4 个类及元类，共 8 个对象。独立读取原始 cache 与实际候选，逐项比对 277 个方法的名称、类型、实现地址，以及 10 个协议名称和正确的空方法缓存绑定。八项损坏的解码引用夹具、四项实际候选字节篡改被拒绝；既有 Foundation 的 pack/environment 元数据与五项损坏记录检查也通过。这些是结构与身份核验，不是全部 AppKit API 的运行证明。

暂存工具还修复了将所有框架写为 Versions/A 的问题。AppKit 现在保留原始 Versions/C，Current 链接指向 C，未版本化入口解析到相同原版字节。错误的 v135 阶段和失败 overlay 日志保留；选中的 v136 从 v134 扩展，不继承错误的 AppKit 路径。

## 实际工程状态

完整原版 Unity/CocoaPods workspace 两次进入五 target 依赖图，UTI 预检通过，原版 xcodebuild 和外层进程均正常返回 65。第一次越过 SIMD 常量后停在 SwiftUI 需要的 AppKit NSBridgedAnimationVector 协议。选入原版 AppKit 及依赖后，两个资源工具与完整工程一致，停在 ApplicationServices 的 kAXElementOrderHorizontalKey。

目前 CompileC 为零，uEmuera、UnityFramework、AFNetworking 最终二进制均不存在。资源编译、完整 Unity/UE App 链接及签名、证书签名和 archive/export 仍未完成；默认安装候选没有提升。先前启动超时的根因也未被本轮证明修复。

下一项已核对：ApplicationServices 原版外层映像没有可执行代码，含 80 字节版本常量和两个版本符号；真实重导出链最终指向嵌入的 HIServices。需要扩展严格的原版 facade 检查器以支持这种形态，保留原始数据/符号/依赖，并恢复真实提供者，不应编造 AX 常量。

## 开发者复现

需要完整本地开发工作区、自行提供的锁定 Intel cache/提取件、Xcode/SDK、Darling 和 LLVM。payload 相对于工作区；合并 pins、源码和历史 revisions 时保留开发者修改与已有 target。公开包不含 Apple/Unity 二进制、SDK、cache、XIP、证书或私钥。XIP 本身不能提供本实验使用的全部系统框架。

```bash
python3 scripts/stage-resource-double4-matrix.py \
  --configuration config/direct-resource-tool-environment-v86.json --tag my-v1
python3 scripts/test-original-swift-singleton-objc.py \
  --target appkit-patch-got-v2 --symbolic-reference 0x7ff808259110 \
  --output artifacts/my-singleton-contract.json
python3 scripts/inspect-swift-singleton-objc-candidate.py \
  --target appkit-patch-got-v2 --output artifacts/my-singleton-inspection.json
python3 scripts/probe-direct-resource-tools.py \
  --stage artifacts/private-procfs-v11-stage.json \
  --configuration config/direct-resource-tool-environment-v88.json
```

最后一个命令当前应报告 kAXElementOrderHorizontalKey 缺失。不要把工具的版本查询、格式检查或元数据检查当作资源编译成功。新的 tag、报告和阶段目录必须采用新名字，不能覆盖已映射库和既有证据。所有原生命令串行使用同一会话锁，清除 DISPLAY、WAYLAND_DISPLAY、XAUTHORITY。

reference/original-file-map.json 保存原始文件路径与 SHA；日志和历史源码用 JSON text 封装，解码后可核对原始 SHA。reference/summary 仅是本地大报告的摘要，不能直接作为运行配置输入。Foundation 回归测试只将原有测试输出路径换成新名字，保留旧结果；没有改变其断言或测试逻辑。

当前进度以 reference/artifacts/simd-appkit-resource-progress-v2.json 为准，类表成员核对见 appkit-singleton-registration-inventory-v1.json。v1 记录保留原始字节；其 additional 字段将全部核验范围标成新增范围，已在 v2 分开统计。
