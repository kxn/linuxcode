# 原版认证、目录与媒体依赖的加载恢复

本附件保存 14 个原版 Intel framework 候选和资源工具加载修复：LocalAuthentication、LocalAuthenticationCore、其嵌套 SharedUtils、OpenDirectory、CFOpenDirectory、MediaToolbox、CoreAUC、CoreMedia、login、VideoToolbox、SkyLight、IOKit、AppleVA、BackBoardHIDEventFoundation。具体来源与输出 SHA 见 candidate-inventory.json。

独立检查核对原始可执行节、VM 相对位置和实际序列化绑定；原版 Xcode dyld_info 接受全部 14 个候选，并拒绝各自的损坏头部与绑定段副本。实际候选的内存副本还接受代码、绑定符号等损坏对照。格式检查不证明 framework API、初始化、资源编译或 App 运行正确。

## 嵌套 framework 的真实搜索规则

Darling 使用的经典 dyld 在 getFrameworkPartialPath 中通过 strrstr 找到最内层 `.framework/`。例如 LocalAuthentication.framework/Support/SharedUtils.framework/Versions/A/SharedUtils，需要把包含 SharedUtils.framework 的 Support 目录加入搜索路径。

仅保留嵌套目录树仍不足以找到库。早期附件对“扁平副本不能满足嵌套安装名”的解释不准确；旧 vImage 环境同时有扁平与嵌套副本，经典 framework 搜索可以命中扁平副本。本附件保留原生树，并明确暴露各嵌套 framework 的父目录，不改写安装名。

extend-resource-framework-overlay.py 在新目录合并经过校验的原版树，生成 extra_framework_paths；direct-resource-tool-runtime-profile.py 仅在 actool / ibtool 的环境中使用这些路径。正常调用方的 framework/library 路径保持原有范围。实际对照保留：第一次 LocalAuthentication 候选找不到 SharedUtils；增加准确搜索根后继续到 OpenDirectory，再到 MediaToolbox、CoreMedia。

IOKit 的原版候选同样只选入资源工具环境；它不替换普通构建服务使用的 Darling IOKit 后端。其硬件调用与服务协议仍未获得整体行为验证。

## 不完整符号表的诊断与严格恢复

SkyLight 的原始跳转桩引用了一批不在已提取 nlist 中的共享 GOT 单元。旧构建器在覆盖检查处直接退出，尚未输出可供独立审计的缺口。

rebuild-c-cache-image.py 现在在该失败路径记录原始桩的真实 GOT 指针，再拒绝生成库；没有放宽覆盖检查。audit-original-stub-got.py 另行只读检查原始桩、指针与所在节，使用原始 nlist 基线，不应用新 pin 的 cache_imports；其 uncovered 数量不是最终候选的未解析绑定数量。随后由已有导出审计和候选准备器分别回读原始依赖，核对名字、地址及来源 SHA。

SkyLight 的 319 项缺失引用通过直接原始导出完成审计；转导出遍历的歧义结果也保留，没有任意选择同地址函数。新候选保留 243 个原始 Objective-C 类、2728 个已验证共享 GOT 单元和原始指令。相同诊断随后用于 BackBoardHIDEventFoundation 的 40 项引用恢复。

实际二进制损坏测试还修正了一个测试选择问题：同一个 SET_SYMBOL 可能被后续状态覆盖。测试现在改坏所选 GOT 符号的全部编码副本，确保检查的是实际绑定，而不是未被使用的中间状态。

## 尚未闭合的 ProDisplayLibrary

最新资源进程到达 SkyLight 后，需要 ProDisplayLibrary 的真实 Swift 类型描述符。ProDisplayLibrary 候选仍拒绝输出：406 项引用中，当前导出审计有一项无法从直接导出或显式符号转导出确定身份。

只读诊断发现对应 libsystem_m 地址有四个数学函数别名；原始共享缓存 GOT 记录明确写的是 `_scalbn`，而 libSystem 能通过整库转导出解析该名称。该记录保存在 prodisplaylibrary-original-math-GOT-identity-v1.json，但目前没有把它作为新兼容绑定应用。下一步需要为这种原始 GOT 身份和整库转导出增加独立验证，再生成新候选；不能直接任选同地址函数。

WatchdogClient 与 libswiftVideoToolbox 的另两个候选也已准备，但尚未选入本附件的资源配置，不计入上述 14 个已选择并完成格式校验的候选。

## 复现与验证边界

payload 路径相对于完整开发工作区，需要与前序研究附件和固定开发环境合并。reference 保存精确输入、独立检查、原版校验与实际失败。日志以 JSON 的 text 字段保存精确 UTF-8 内容，可按 original-file-map.json 解码并核对原始字节 SHA；历史 Python 源码使用 SHA.py 文件名。summary 下明确标记的报告仅为摘要，完整本地报告由 SHA 引用，不能当成可直接加载的 stage。

在保留对应 Intel 缓存、提取映像、Xcode/SDK 和前序运行根的全新实验工作区，可按 reference/artifacts 中对应 input.json 的 command 及 payload 的锁定 pin 重建候选。输出目录、stage 和日志必须使用未占用名字，不能覆盖已映射的库。

```bash
python3 scripts/audit-original-stub-got.py \
  --target skylight-patch-got-v3 --output artifacts/my-stub-diagnostic.json
python3 scripts/test-resource-image-preparation.py
python3 scripts/test-reexport-resource-preparation.py
python3 scripts/test-preserved-patch-got-inspector.py
python3 scripts/probe-direct-resource-tools.py \
  --stage artifacts/private-procfs-v11-stage.json \
  --configuration config/direct-resource-tool-environment-v60.json
```

运行探测前必须先在本地重建、生成并校验配置引用的 stages。Darling 会话串行，DISPLAY / WAYLAND_DISPLAY / XAUTHORITY 被清除；工具和工程命令继续使用原版。

实际原版 Unity/CocoaPods 构建和资源工具的最终结果见 evidence.json。版本查询、结构通过和依赖加载均不等于完整资源编译成功。Unity/UE 的 App 链接、签名、设备运行、provisioning 及 archive/export 仍需完成，默认安装环境没有提升。

此附件不是干净机器的一键安装包。Xcode XIP 不提供额外的系统共享缓存；这些输入仍需由使用者在本地提供。公开内容仅含源码、文档和元数据，不含 Apple/Unity 二进制、SDK、缓存、XIP、证书或私钥。
