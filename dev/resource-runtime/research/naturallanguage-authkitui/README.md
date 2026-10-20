# Swift NaturalLanguage、AuthKitUI 与整库重导出

纯 Linux x86_64 / Darling，无界面。选用 direct-resource-tool-environment-v105.json、graphics v152 与 crashreportersupport overlay；原版 Xcode 工具、Unity/CocoaPods 工程及 CI 参数保持不变。

恢复原版 Swift NaturalLanguage、AuthKitUI、IASUtilities、JavaScriptCore、IASUtilitiesCore、libParallelCompression、CrashReporterSupport 七个映像，核验 2937 个 GOT 单元及 5951 个绑定，可执行节字节保持一致。原版 dyld_info 的七个格式正例和十四个损坏对照通过；实际候选的代码与绑定篡改也被拒绝。这些检查不代表全部框架 API 已兼容。

## 原始命名空间和数据

AuthKitUI 的 25 个 Swift 导入经 SwiftUI 的 LC_REEXPORT_DYLIB 声明指向 SwiftUICore，不能仅从 SwiftUI 自身的逐符号导出中找到。新审计选项仅对显式指定、且原本就在依赖表中的提供者跟踪整库重导出，保留原始查找次序，并记录沿途原版文件哈希。准备工具会独立重算该证明，未知或歧义导入仍拒绝。没有将 SwiftUICore 添加为猜测的新依赖。

实际 AuthKitUI 的 126 个导入行全部核实，其中恢复上述 25 个。两项真实 Mach-O 声明变更对照验证了限制：删除 SwiftUI 到 SwiftUICore 的重导出后，25 项重新未解析；构造重导出环被拒绝。未声明的顶层提供者也被拒绝。既有 SoundAnalysis 的 990 行逐符号审计及其证明保持完全一致。IASUtilities 与 JavaScriptCore 的 recvfrom/scalbn 系列导入通过原始 GOT patch 身份核实，没有按共享函数地址猜名字。首次失败候选与审计记录保留。

CrashReporterSupport 的 kCRProblemReportAppNameKey 实际原始字符串为 name。通过真实 CoreFoundation API 核验其非零类型 ID 7、UTF-8 值、实际提供者和默认命名空间的指针身份；旧配置重现符号缺失，错误值对照被拒绝。嵌入 LAPACK/BLAS 的目录随新 overlay 迁移，两个库的字节保持一致；没有覆盖已映射库。

## 完整工程与下一步

原版 actool/ibtool 已越过 NaturalLanguage、AuthKitUI 及 CrashReporterSupport 缺口。完整 Unity/CocoaPods workspace 进入五 target 依赖图，UTI 预检通过，原版 xcodebuild 与外层进程正常返回 65；最终与直接探针一致，停在 JavaScriptCore 所需的 os_script_config_storage。

已对照当前原版 libsystem_platform 映像和 [WebKit 开源代码](https://github.com/WebKit/WebKit/blob/3d023cd1e358acd0ab194640ea997d61e2e8e074/Source/JavaScriptCore/llint/LLIntData.cpp) 核实：这是原始全零、16 KB、x86 页对齐的存储，调用者负责初始化与页面保护。尚未实现或运行验证。下一步要补齐真实存储契约并验证隔离和保护行为，再继续资源工具。

CompileC 仍为零，uEmuera、UnityFramework、AFNetworking 最终二进制不存在。资源编译、完整 Unity/UE App 链接与签名、证书签名及 archive/export 尚未完成；默认安装候选没有提升。历史启动超时根因仍未证明修复。

## 开发者复现

需要完整本地开发工作区、自行提供的锁定 Intel cache/提取件、Xcode/SDK、Darling 与 LLVM。公开附件只含源码、配置、公开 WebKit 参考和文字证据，不含 Apple/Unity 二进制、SDK、cache、XIP、证书或私钥；XIP 不包含全部系统框架。两份故意修改声明的 Mach-O 对照仅保存在本地，不在公开包中。payload 路径相对工作区；合并 pins 与历史 revisions 时保留已有 target 和开发者修改。reference/summary 是大报告摘要，不能作运行输入。

```bash
python3 scripts/test-whole-library-reexport-imports.py \
  --output artifacts/my-whole-reexport-controls.json
python3 scripts/probe-original-framework-cfstring.py \
  --configuration config/direct-resource-tool-environment-v105.json \
  --baseline-probe runtime/direct-resource-tools-phwgzgym/result.json \
  --contract artifacts/crashreportersupport-original-string-contract-v1.json \
  --stage artifacts/private-procfs-v11-stage.json
python3 scripts/probe-direct-resource-tools.py \
  --stage artifacts/private-procfs-v11-stage.json \
  --configuration config/direct-resource-tool-environment-v105.json
```

前两项应通过，最后一项当前应失败于系统存储符号缺失。完整工程参数为 unity-ios-cocoapods-v62-probe-arguments.json，重跑使用新的 DerivedData。原生命令串行执行，清除 DISPLAY、WAYLAND_DISPLAY、XAUTHORITY，使用新的阶段、日志与报告名称。reference/original-file-map.json 保存路径与 SHA，日志及历史源码采用 UTF-8 JSON text 封装；进度以 reference/artifacts/naturallanguage-authkitui-resource-progress-v1.json 为准。
