# Settings、GeoToolbox 与 Swift 元数据边界

纯 Linux x86_64 / Darling、无界面。配置 v110、graphics v155、geotoolbox overlay；原版 Xcode 工具、Unity/CocoaPods 工程和 CI 命令保留。

恢复 Settings 的 61 个原版依赖映像和随后由实际资源工具触发的 GeoToolbox。独立核验 30567 个 GOT 单元、140206 个绑定及 56193852 字节原版可执行内容。62 个原版 dyld 格式正例、124 个损坏对照及实际代码/绑定篡改检查通过。这不证明所有框架 API 的运行兼容。

## Swift 和原始导入身份

HealthKit 的泛型环境包含 Codable、Hashable、Sendable。原版 Swift 编译器实际生成头部计数四、只写出三个真实协议要求的布局；Int/String/Bool 三类实例的 12 次 KeyPath 读写成功。新解析器只接受该经过复现的标准协议形状，核验原始局部符号边界、44 字节哈希、同一个泛型参数、Decodable/Encodable/Hashable 的原始定义身份及名称。保留头部计数和全部原始字节；12 个错误对照拒绝。未知布局仍拒绝。

GRDBInternal 中被剥离符号的五个泛型环境由 13 个明确固定的原版 KeyPath 模式识别。发现步骤只供研究，准备工具独立验证每个模式，重建过程不做字节扫描。ChronoServices 的 lround 和 EmailFoundation 的 llroundl 由原始 stub/GOT 与 cache patch 记录核实，没有按共享地址挑选数学函数别名。VoiceShortcutClient 通过 LinkServices 的原始整库重导出查找 LinkMetadata。批处理仅传递配置中明确列出的审计选项，原有缺省行为保留。

## 独立格式检查

LLVM 19 将首个节地址误当作段地址，既可能报不在节内，也可能报跨越节尾。新证明匹配实际报错的绑定指令偏移，核验真实段地址下的八字节写入有效，并重现 LLVM 的错误地址计算；仍要求对应原版 dyld 正例与损坏对照通过。旧解析器与新解析器对 61 个映像的 122 条绑定流解码结果完全相同，六个错误诊断对照被拒绝。未知 LLVM 错误不会被接受。

上述布局参考公开 [Swift GenProto.cpp](https://github.com/swiftlang/swift/blob/swift-6.3.3-RELEASE/lib/IRGen/GenProto.cpp) 与 [GenMeta.cpp](https://github.com/swiftlang/swift/blob/swift-6.3.3-RELEASE/lib/IRGen/GenMeta.cpp)；LLVM 根因可对照 [LLVM 19.1.7 MachOObjectFile.cpp](https://github.com/llvm/llvm-project/blob/llvmorg-19.1.7/llvm/lib/Object/MachOObjectFile.cpp)。公开参考保留原始许可证头。

## 当前构建结果

完整 Unity/CocoaPods workspace 的五 target 依赖图与 UTI 预检通过，原版 xcodebuild 实际返回 65。最新阻塞为 _$s18CommunicationTrust9BlockListCMa。CompileC 为零，最终 App/UnityFramework/AFNetworking 二进制不存在。资源编译、完整 Unity/UE 链接、签名及 archive/export 尚未完成；默认安装候选未提升。独立 JavaScriptCore 上下文创建仍停在 liboah 的 dyld API 缺口，脚本存储的永久冻结语义尚未验证。

## 开发者复现

需要完整 Linux 工作区、自行提供的锁定 Xcode/SDK、Intel cache/提取件与 Darling/LLVM；XIP 不含所有系统框架。附件仅含源码、配置、文本证据与历史，不含 Apple/Unity 二进制、SDK、XIP、证书或私钥。payload 相对工作区；合并 pins/历史时保留已有 revisions。summary 只供阅读，不能作为运行输入。所有原生运行串行执行，使用新的报告、tag、DerivedData，并清除 DISPLAY/WAYLAND_DISPLAY/XAUTHORITY。

```bash
python3 scripts/test-original-swift-codable-marker-environment.py
python3 scripts/test-swift-environment-marker-bounds.py --compiler-proof runtime/your-new-swift-probe/result.json --output artifacts/my-healthkit-marker-controls.json
python3 scripts/test-llvm-first-section-error-proof.py --output artifacts/my-llvm-first-section-controls.json
python3 scripts/probe-direct-resource-tools.py --configuration config/direct-resource-tool-environment-v110.json --stage artifacts/private-procfs-v11-stage.json
```

第一条打印新 EVIDENCE 路径，将其填入第二条 compiler-proof。其余研究检查使用本检查点的固定候选和已保存的格式验证报告；它们不能替代在新环境重新运行原版工具。最后一项当前仍失败。完整工程参数为 unity-ios-cocoapods-v66-probe-arguments.json，重跑需新 DerivedData。reference/original-file-map.json 记录原始路径和 SHA，日志、上游参考和历史源码以 UTF-8 JSON text 封装。
