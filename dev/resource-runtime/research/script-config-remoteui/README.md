# 系统脚本存储与 RemoteUI 依赖

纯 Linux x86_64 / Darling、无界面。配置 v108，graphics v153，remoteui overlay。原版 Xcode 工具、Unity/CocoaPods 工程及 CI 命令保留。

实现 os_script_config_storage 的真实 16 KB 全零存储，4096 字节对齐、独立数据节。调用者负责初始化和保护，没有预填脚本操作码或修改脚本权限判断。原生验证初始全零、全区写读、fork 写入隔离、独立进程归零，以及四个页面设为只读后写入确实触发访问异常。尚未证明永久冻结语义，也未成功创建原版 JavaScriptCore 执行上下文；独立 C API 探针停在 liboah 的 dyld_shared_cache_for_each_subcache4Rosetta 导入。首次暂存遗漏既有 SIMD 辅助库的失败记录保留，v2 修复并保留其原始字节。

恢复原版 RemoteUI、LiftUI、_IconServices_SwiftUI，3291 个 GOT 单元、6150 个绑定经过独立检查；原版可执行字节保持一致。三个原版格式正例、六个损坏对照及候选代码/绑定篡改对照通过。这些属于格式与绑定检查，不证明全部框架 API。

新增可选的同名重导出合并：仅在原版显式重导出链都到达同一个定义提供者、同一个符号，且该提供者本身就在原始候选中时采用。RemoteUI 的 CGFloat 元数据满足该条件；不同定义仅地址相同、改名符号、缺失导出、错误地址、非法 ordinal 和循环均拒绝。准备工具独立重算证明。旧的 990 行逐符号审计及 25 个受限整库重导出检查继续通过。

完整 Unity/CocoaPods workspace 的五 target 依赖图和 UTI 预检通过，xcodebuild 实际返回 65，当前阻塞 _$s8Settings0A8IconViewV5StyleOMa。CompileC 为零，最终 App/UnityFramework/AFNetworking 二进制不存在。资源编译、完整 Unity/UE 链接、签名和 archive/export 尚未完成，默认安装候选未提升。

源码修改已保存到 [kxn/darling-libplatform](https://github.com/kxn/darling-libplatform/commit/f0e056d175881f43eb115442dba84e051891c035)，提交者与作者均为 Comman Kang。存储契约参考公开 [WebKit LLIntData.cpp](https://github.com/WebKit/WebKit/blob/3d023cd1e358acd0ab194640ea997d61e2e8e074/Source/JavaScriptCore/llint/LLIntData.cpp)。

开发者需自行提供锁定的 Xcode/SDK、Intel cache/提取件及完整 Darling 工作区；XIP 不包含所有系统框架。本附件仅发布源码、配置、文本证据及历史，不含 Apple/Unity 二进制、SDK、XIP、证书或私钥。payload 相对工作区；历史需合并并保留已有 revisions。summary 只供阅读，不能作为运行输入。所有原生探针串行执行，重跑使用新 tag、报告和 DerivedData，清除 DISPLAY/WAYLAND_DISPLAY/XAUTHORITY。

```bash
python3 scripts/test-equivalent-original-reexports.py --output artifacts/my-equivalent-controls.json
python3 scripts/probe-script-config-storage.py --configuration config/direct-resource-tool-environment-v108.json --baseline-probe runtime/direct-resource-tools-izx1ygtg/result.json --stage artifacts/private-procfs-v11-stage.json
python3 scripts/probe-direct-resource-tools.py --configuration config/direct-resource-tool-environment-v108.json --stage artifacts/private-procfs-v11-stage.json
```

前两项应通过；最后一项当前仍失败。完整工程参数为 unity-ios-cocoapods-v64-probe-arguments.json。reference/original-file-map.json 记录原路径和 SHA；原始日志和历史源码以 UTF-8 JSON text 封装。
