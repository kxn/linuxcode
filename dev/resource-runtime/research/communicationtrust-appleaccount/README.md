# CommunicationTrust、只读 UUID 与 AAResponse 布局

纯 Linux x86_64 / Darling、无界面。配置 v113、graphics v157、appleaccount overlay。原版 Xcode 工具、Unity/CocoaPods 工程与 CI 命令保留。

恢复 CommunicationTrust、CallsPersistence、SensitiveContentAnalysis、PeopleSuggester 和 AppleAccount 五个原版映像。独立核验 3025 个 GOT 单元、10399 个绑定；原版可执行字节保持一致。五个原版 dyld 格式正例、十个损坏对照及实际代码/绑定篡改检查通过。这些检查不代表全部框架 API 已兼容。

## 真实数据和类布局

EmailCore 所需的 ne_privacy_dns_netagent_id 是 libsystem_networkextension 的只读 16 字节数据。原始地址、相邻导出及字节已核实。新定义使用 SDK 的 uuid_t 并断言其大小，保留原始 UUID 值和只读属性；没有增加网络服务函数。新 libSystem 只添加命名重导出，保留完整的二十个初始化/队列源码单元、既有导出负载及 SIMD/脚本存储辅助库原始字节。原生验证 uuid_parse/uuid_compare/uuid_unparse_upper、默认命名空间身份、实际提供者和写入时的访问异常；旧配置返回缺失，错误 UUID 被拒绝。网络服务 API 仍未证明兼容。

AppleAccount 使用完整原版类定义，未猜测 AAResponse._error 的偏移。原始偏移 24、实例大小 64。原生 libobjc 的 ivar_getOffset 与导出单元一致；写入真实 NSError 后，原版 getter 取回同一对象，错误码 73 正确；同时核验原版 getter 的实际提供者。旧配置重现变量缺失，错误偏移对照被拒绝。未执行完整账户服务或证明全部 AppleAccount API。

Darling 源码已保存到 [kxn/darling](https://github.com/kxn/darling/commit/95a5bf99a156f75ecc340a246c90275f0b88954a)，沿用既有分支，作者和提交者均为 Comman Kang。

## 当前完整工程

完整 Unity/CocoaPods workspace 进入五 target 依赖图，UTI 预检通过，原版 xcodebuild 与外层进程返回 65。当前与两个直接探针一致，停在 EventKit 的 EKEventStoreChangedNotification；已核实原版字符串值，但尚未恢复该提供者。CompileC 为零，最终 App/UnityFramework/AFNetworking 二进制不存在。资源编译、完整 Unity/UE 链接、签名及 archive/export 尚未完成，默认安装候选未提升。原版 JavaScriptCore 上下文创建和脚本存储永久冻结语义仍未验证。

## 开发者复现

需要完整本地开发工作区、自行提供的锁定 Xcode/SDK、Intel cache/提取件以及 Darling/LLVM。XIP 不含所有系统框架。附件只发布源码、配置和文本证据，不含 Apple/Unity 二进制、SDK、XIP、证书或私钥。payload 相对工作区，历史需合并并保留已有 revisions。summary 不能用作运行输入。所有原生运行串行执行，使用新的 tag、输出报告和 DerivedData，清除 DISPLAY/WAYLAND_DISPLAY/XAUTHORITY。

```bash
python3 scripts/probe-ne-agent-uuid.py --configuration config/direct-resource-tool-environment-v113.json --baseline-probe runtime/direct-resource-tools-ntkda537/result.json --stage artifacts/private-procfs-v11-stage.json
python3 scripts/probe-appleaccount-response-ivar.py --configuration config/direct-resource-tool-environment-v113.json --baseline-probe runtime/direct-resource-tools-_z5cyk2z/result.json --stage artifacts/private-procfs-v11-stage.json
python3 scripts/probe-direct-resource-tools.py --configuration config/direct-resource-tool-environment-v113.json --stage artifacts/private-procfs-v11-stage.json
```

前两项应通过，最后一项仍失败。上述比较使用本检查点固定的基线报告；新环境需重新生成相应基线。完整工程参数为 unity-ios-cocoapods-v69-probe-arguments.json。reference/original-file-map.json 记录原路径与 SHA；日志和历史源码以 UTF-8 JSON text 封装。
