# 原版 AVFAudio 转导出与符号表分组修复

本附件继续在纯 Linux x86_64 / Darling 中运行原版 Xcode 工具。它恢复 AVFAudio 的原版指令和 AudioSession 转导出，不构造通知常量或替代类。完整 Unity/UE App 的资源编译、链接和签名仍未完成；默认安装候选没有提升。最新实际构建见 evidence.json。

## 保留真正的转导出

MediaRemote 需要 AVFAudio 的 AVAudioSessionRoutingContextChangeNotification。原始导出表证明，AVFAudio 把它转导出到第九个依赖 AudioSession，后者实际定义这个全局对象；已有 AudioSession 候选已包含它。

首次 AVFAudio 构建因两个未解析的 Swift 元数据引用停止，未输出库。独立原始导出审计确认 UInt32 和 ContiguousArrayStorage 的真实描述符，再由准备器重新核验并选择，未按邻近地址猜符号。后续候选保留全部可执行指令、661 个 GOT 单元和 1531 个序列化绑定，没有 backend-call override。

原生对照先确认旧 AVFAudio 提供者没有该转导出，再通过 RTLD_FIRST 查询新 AVFAudio 和 AudioSession。两个句柄返回同一符号槽位和同一 CFString 对象；dladdr 明确属于当前 AudioSession 候选。实际 CFString 类型、长度和 UTF-8 内容均与原始缓存读取的值一致。

这证明了此转导出和常量对象，不代表整个音频框架 API 或音频硬件功能已验证。框架及工具的原版代码继续执行，Darling 会话串行且清除 DISPLAY、WAYLAND_DISPLAY、XAUTHORITY。

## 修正提取件末尾的别名分组

苹果原版 dyld_info 拒绝第二份候选，报告 symbol count 与 dynamic symbol table 不同。直接读取共享缓存头得到 7162 个符号，原有三组计数之和也是 7162；提取件另在末尾增加了 166 个外部 N_INDR 自名转导出别名，LC_SYMTAB 成为 7328，而 LC_DYSYMTAB 未将它们计入。

normalize-dysymtab-aliases.py 只支持这个已确认的布局：原局部组、定义组、未定义组、追加别名。它保留每个完整 nlist 记录、字符串和别名目标，把别名放入外部定义组，并同步更新组边界及需要变化的间接符号索引。未识别的尾部类型、非连续边界、无效字符串/索引和未建模的索引侧表均拒绝处理。

AVFAudio 的最终分组为 6090 个局部符号、435 个外部定义、803 个未定义符号。其 1179 项间接表在这份实际输入中没有需要改变的索引，全部保留。具有受影响未定义引用的情况由明确标记的内存夹具和单元测试覆盖，没有把夹具引用说成原始映像中的引用。

独立验证器根据实际 nlist 类型稳定分组，不复用归一化器的映射或报告。它核对全部符号名、描述符、别名目标、规范化地址及间接符号身份。七项真实二进制篡改负例全部拒绝；另有带引用的夹具负例及真实、已正常分组映像的字节不变对照。八项单元测试还覆盖未建模侧表等拒绝分支。

修复后的第四份候选通过苹果 dyld_info；损坏加载命令和绑定段的两个副本均被拒绝。第二份失败候选、第一次缺少 audit 的准备调用、旧源码与日志全部保留，未覆盖失败。v117 仅为未选用的实验目录；最终 v118 从此前有效的 v116 派生，未继承失败候选。

## 在完整开发基线上复现

需要此前附件的完整源码/运行基线、本地锁定 Intel cache 与提取件、Xcode/SDK、LLVM 19，以及私有运行根。payload 相对于完整工作区，应审阅合并并保留精确源码 SHA 历史。所有输出必须使用新名称。

```bash
python3 scripts/test-dysymtab-alias-normalization.py
python3 scripts/prepare-resource-image-candidate.py \
  --image /System/Library/Frameworks/AVFAudio.framework/Versions/A/AVFAudio \
  --target my-avfaudio-initial --preserve-code-with-patch-got \
  --patch-got-renamed-reexports --preserve-original-uuid --read-only-data-const \
  --align-linkedit-streams --omit-lazy-helper-section --omit-leading-padding-sections --build
```

若准备器因未解析的导入拒绝输出，先以 audit-resource-image-imports.py 审计实际缺失项，再用原 target、实际 audit 和新 target 调用准备器。--from-target 要求提供可重新核验的 exact-import-audit，不能当作无条件复制入口。

候选仍须运行 inspect-preserved-patch-got.py、test-dysymtab-alias-binary.py、test-preserved-patch-got-binaries.py 和原版 dyld_info 对照。独立检查器对修复过的候选自动调用新符号表验证器；不将 LLVM 的首节基址限制当成通过，仍要求苹果原版正例及损坏对照。

在自己建立的新 graphics/overlay 和配置上，可验证实际转导出：

```bash
python3 scripts/probe-avfaudio-reexport.py \
  --configuration config/my-resource-environment.json \
  --baseline-configuration config/direct-resource-tool-environment-v69.json \
  --stage artifacts/private-procfs-v11-stage.json \
  --original-value artifacts/avfaudio-original-notification-value-v1.json
```

原始值报告包含原始 AudioSession SHA、缓存地址、CFString 标志和值，见 reference。native probe 使用 classic fixup 输出；首次链接夹具选错 fixup 格式的失败也保留。新配置只能填写自己实际构造的 stage 路径和 SHA，不能把参考工作区路径当作可直接使用的安装成果。

原版 actool/ibtool 已越过 AVFAudio 缺失，当前遇到 ScreenTimeCore 所需的 Contacts 类 CNDowntimeWhitelist；完整构建和产物检查保留真实状态，不用版本查询代替资源编译。reference 日志用 JSON text 保存原始 UTF-8 字节，original-file-map.json 提供 SHA；summary_only 文件只是完整本地报告摘要。公开包不含 Apple/Unity 二进制、SDK、cache、XIP、证书或私钥。
