# 原版 MobileAsset 与 AVFoundation 转发框架

本附件继续在纯 Linux x86_64 / Darling 上运行原版 actool、ibtool 和 Unity/CocoaPods 工程。完整 Unity/UE App 的资源编译、链接和签名仍未完成，最新完整工程结果、实际缺口与产物检查见 evidence.json。默认安装候选没有提升。

## 恢复原版提供者

UnifiedAssetFramework 需要 MobileAsset 的 MAThirdPartyCompatibility 类。原版 MobileAsset 和其缺失强依赖 SoftwareUpdateCoreSupport 已恢复，独立检查核对 416 个 GOT 单元和 4050 个绑定，保留全部原版可执行节字节。原版 dyld_info 正例及损坏对照通过后，graphics v122 / mobileasset-closure-v1 overlay 仅加入资源工具子进程作用域。

原版工具随后越过该类缺失，暴露 InertiaCam 需要 AVVideoCodecTypeHEVC。原始缓存确认该常量经 AVFoundation 的重导出提供，实际实现在 AVFCore。恢复 AVFCore、AVFCapture 并校验原始导入身份；两份映像通过独立代码、GOT、绑定、实际二进制损坏控制和原版格式检查。

原版 AVFoundation 本身不含函数体：它只有零长度 __text、一个八字节 Objective-C image-info 记录和四条框架重导出。通用 GOT 模式因不存在 GOT 而拒绝它；普通函数分析也因不存在函数入口而拒绝。两次失败均保留，没有虚构 GOT 或函数来满足准备器。

## 为无代码转发框架增加明确路径

prepare-resource-image-candidate.py 新增 --reexport-facade。original-reexport-facade.py 只接受实际核验的无代码结构，要求原始重导出、无符号/导出/函数记录及固定的 image-info 布局。它不允许与 GOT 模式或导入审计克隆混用。普通带代码的 MobileAsset 实际输入和混合模式均必须在修改清单前失败；六项既有准备器回归也通过。

该模式继续使用原有重建器；它只省去对此明确无代码结构的函数分析。独立检查核对原始 UUID、安装身份、平台/SDK 和所有依赖命令字节，拒绝新增代码、符号、绑定、导出或初始化命令。image-info 仅清理重建器既有的缓存预优化标志，原始四条重导出命令逐字节不变。这里没有实现视频编解码算法或填入替代 HEVC 值。

probe-original-reexport-facade.py 检查真实候选，并在内存中损坏真实结构：新增代码长度、篡改 image-info、改变提供者、把重导出改成普通加载、修改 UUID、加入初始化命令及非空原始代码，七种情况全部必须拒绝。原版 Apple dyld_info 随后检查有效候选及命令长度、依赖名称偏移两个损坏副本，读取原生命令状态。无绑定的转发框架使用依赖名称损坏对照，不伪装成存在可破坏的绑定项。

graphics v123 / avfoundation-closure-v1 overlay 加入三份原版候选后，原版工具越过 HEVC 常量缺失，推进到 CMCapture 所需的 CoreMediaIO 类 CMIOExtensionProvider。CoreMediaIO 已恢复并通过原版格式及独立代码/绑定检查，加入 graphics v124 / coremediaio-closure-v1 后，原版工具继续推进到 libswiftAVFoundation 的 AVAsyncProperty 类型元数据缺失。该原版 Swift 库也已通过格式和独立检查，但尚未加入选择环境。文件或格式存在不代表摄像头服务及整个 CoreMediaIO API 已兼容。

## 完整工程的启动等待

本轮保留了一次完整原版 Unity/CocoaPods 尝试：UTI 预检通过，xcodebuild 确实启动，但测试框架在 600 秒后终止，未获得原版返回状态，没有 CompileC 或最终 App。它不能记作退出 65 或构建成功。实时栈显示先前的 CarbonCore 文件 ID 查询等待后来恢复；后两次栈均位于 CoreSimulator 服务加载重试的 usleep(250000)。

保存的 PC/映像按实际 x86_64 fat slice 与段映射重新符号化，核对映像 inode 和 SHA；初次最近符号注释只是诊断线索。相同运行层的串行/四工作线程共十六次 usleep 实测通过，不能据此证明 CoreSimulator 等待的原因。启动可靠性仍需继续排查。

## 开发者复现

payload 相对于完整开发工作区，需要此前附件、锁定的 Intel cache/提取件、Xcode/SDK 和 LLVM。清单是实验快照，合并时保留其他 target；运行时使用自己的新 target/tag，不覆盖已映射库或旧证据。

```bash
python3 scripts/prepare-resource-image-candidate.py \
  --image /System/Library/Frameworks/AVFoundation.framework/Versions/A/AVFoundation \
  --target my-avfoundation-facade-v1 --reexport-facade \
  --preserve-original-uuid --read-only-data-const --align-linkedit-streams \
  --omit-lazy-helper-section --omit-leading-padding-sections --build
python3 scripts/probe-original-reexport-facade.py \
  --target my-avfoundation-facade-v1 --stage artifacts/private-procfs-v11-stage.json
```

报告只证明候选结构及原版格式；仍需完整依赖和实际原版工具/工程验证。原生命令串行并清除 DISPLAY、WAYLAND_DISPLAY、XAUTHORITY，不启动图形界面。reference 中日志以 JSON text 保存原始 UTF-8 字节，original-file-map.json 提供 SHA。summary_only 文件只是完整本地报告摘要。公开包不含 Apple/Unity 二进制、SDK、cache、XIP、证书或私钥。
