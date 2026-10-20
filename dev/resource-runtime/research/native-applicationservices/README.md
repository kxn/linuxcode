# 原版 ApplicationServices 重导出与嵌入框架

纯 Linux x86_64 / Darling、无界面的实验检查点。最终选择 direct-resource-tool-environment-v93.json、graphics v141 和 applicationservices-atsui overlay；原版 Xcode 工具及 Unity/CocoaPods 工程和 CI 参数保持不变。

ApplicationServices 外层映像没有可执行代码，含 80 字节版本常量、两个版本导出和 11 个框架重导出命令。新检查器支持这类真实结构，保留原始数据、符号身份、导出强弱标志、地址、UUID 和依赖命令。它先与原始 cache 的两个导出核对，再检查实际候选；没有伪造 AX 常量或 GOT。首次检查因尚未识别版本导出而拒绝候选，失败记录保留。新候选的八项实际损坏对照通过；另三项仍能解析但名称、地址或强弱标志错误的导出也被拒绝。既有 AVFoundation facade 的原版格式和损坏对照回归通过。

## 本轮恢复与验证

选入原版 ApplicationServices、HIServices、SpeechSynthesis、HIToolbox、QD、ATS、PrintCore、ColorSyncLegacy、ATSUI。八个含代码映像合计核对 5018 个 GOT 单元、11299 个绑定，可执行节字节保持一致；外层 facade 单独比较全部常量及版本符号。九个原版 dyld_info 格式正例与十八项损坏对照通过。这不代表九个框架的 API 全部兼容。

ApplicationServices 与嵌入框架共用外层目录。extend-resource-framework-overlay.py 现在按经过验证的源目录分组，只复制一次共享树，同时逐项核对各 target 的映像；同名树必须指向同一来源，已有 overlay 中的冲突树仍拒绝覆盖。最终九个映像位于 ApplicationServices 和 Carbon 两棵树，原始版本化路径与实际候选字节均核对。

一项真实 Darling 原生程序通过 ApplicationServices 的句柄查找四个 AX 全局，调用 CoreFoundation 将 CFString 转成 UTF-8，逐项比对原始 cache 中的字符串，并检查默认命名空间的指针身份和 dladdr 提供者。四项均通过，实际提供者为新恢复的 HIServices。这项 API 测试使用 v89 配置；最终 v93 复用相同的 ApplicationServices/HIServices 字节，并增加其他原版依赖。没有据此宣称最终配置的全部 API 已验证。

原版资源工具依次越过 AX 常量、SpeechSynthesis 回调常量、HIToolbox 常量、QD 的 SetRect 及 ATSUI 文件缺失。最后一项来自 QD 的实际强依赖。最终 actool/ibtool 一致停在 ReplayKit 需要的 ViewBridge 类 NSRemoteViewControllerParameters。

## 完整工程结果

本轮完整 Unity/CocoaPods workspace 在 v90、v91、v93 配置各运行一次，均进入五个 target 的依赖图，UTI 预检通过，原版 xcodebuild 和外层进程正常返回 65。失败分别为 kHIViewWindowContentID、SetRect 和 NSRemoteViewControllerParameters。

CompileC 均为零，uEmuera、UnityFramework、AFNetworking 的最终二进制仍不存在。资源编译、完整 Unity/UE App 链接及签名、证书签名、archive/export 尚未完成；默认安装候选没有提升。历史启动超时的根因也未被本轮证明修复。

下一项已核对原版 ViewBridge 中存在真正的 NSRemoteViewControllerParameters 类导出。继续准备新候选、核验原版依赖及导入、运行原版格式/损坏对照，再回到原版资源工具和完整工程。未知导入仍需拒绝，不能用空类代替。

## 开发者复现

需要完整本地开发工作区、自行提供的锁定 Intel cache/提取件、Xcode/SDK、Darling 与 LLVM。payload 相对于工作区；合并 pins、源码与历史 revisions 时保留已有 target 和开发者修改。公开附件不含 Apple/Unity 二进制、SDK、cache、XIP、证书或私钥。XIP 本身不提供全部系统框架。

```bash
python3 scripts/probe-original-reexport-facade.py \
  --target applicationservices-reexport-facade-v2 \
  --stage artifacts/private-procfs-v11-stage.json
python3 scripts/test-constant-facade-exports.py \
  --target applicationservices-reexport-facade-v2 \
  --output artifacts/my-facade-export-controls.json
python3 scripts/probe-applicationservices-AX-constants.py \
  --stage artifacts/private-procfs-v11-stage.json \
  --configuration config/direct-resource-tool-environment-v89.json \
  --contract artifacts/hiservices-original-AX-string-contract-v1.json
python3 scripts/probe-direct-resource-tools.py \
  --stage artifacts/private-procfs-v11-stage.json \
  --configuration config/direct-resource-tool-environment-v93.json
```

最后一个命令目前应失败于 ViewBridge 类缺失。中间版本的 build/probe 参数文件也保留，但只有记录中的命令实际执行过。所有原生命令串行使用同一会话锁，清除 DISPLAY、WAYLAND_DISPLAY、XAUTHORITY。新阶段和报告使用新名字，保留失败记录，不覆盖已映射库。

reference/original-file-map.json 保存路径与 SHA；日志和历史源码采用 JSON text 封装，解码后核对原始 SHA。reference/summary 是本地大报告摘要，不能直接作为运行配置输入。当前实际进度见 reference/artifacts/applicationservices-resource-progress-v1.json。
