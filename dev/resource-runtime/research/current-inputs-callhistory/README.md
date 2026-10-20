# 当前运行输入与原版 CallHistory 依赖

本附件在纯 Linux x86_64 / Darling 上选用四个原版映像：Swift AVFoundation、CallsXPC、CallsUtilities、LiveCommunicationKit。实际资源编译、完整 Unity/UE App 链接和签名仍未完成，默认安装候选没有提升。

原版工具依次越过 Swift AVFoundation 类型缺失、CallsXPC 加载失败和 CallsUtilities 协议元数据缺失。CallHistory 的物理依赖清单还发现缺少原版 LiveCommunicationKit，一并恢复。CallsXPC、CallsUtilities、LiveCommunicationKit 首次重建因原始跳转桩 GOT 未覆盖而停止；分别核验 174、64、244 个原始导入身份后才生成新候选，失败尝试均保留。

四份映像独立检查合计验证 1280 个 GOT 单元和 2216 个绑定，原版可执行节字节保持一致。原版 dyld 格式正例与损坏对照、实际候选的代码/绑定篡改拒绝记录均保存。Swift AVFoundation 复用先前已核验且 SHA 不变的格式证据；其他三份执行本轮原版格式检查。这些结果不代表整个框架 API 已兼容。

最新完整原版 Unity/CocoaPods workspace 已进入五 target 依赖图，UTI 预检通过，原版 xcodebuild 返回 65。其资源工具与独立探测一致，失败于 TelephonyUtilities 所需的 CoreTelephony 常量 kCTProvisioningStatus，仍无 CompileC 或最终 App。CoreTelephony 的原版提供者已恢复并验证，但尚未选入运行配置，后续状态见 evidence.json。

## 从启动输入中分离未使用的祖先副本

迭代阶段报告继承了旧版本的文件表：graphics v125 包含 19812 份旧阶段文件，共约 21.16 GB，当前实际目录约 574 MB。资源 overlay 另含约 0.97 GB 旧副本。每次启动重复读取它们，增加了开发验证成本，也让当前候选依赖过多历史目录。

compact-resource-stage-inputs.py 创建一份新的完整阶段报告，不修改库、旧报告或目录。它先验证来源报告的所有 files/links 和明确的 parent_stage / parent_overlay 祖先链，再核对当前目录的完整文件、符号链接清单及链接边界。仅属于明确祖先目录的副本可从启动校验表移入 historical_stage_files / historical_stage_links；其他输入保留。原报告和 SHA 一并保留，历史哈希没有丢弃。历史目录不会被删除，也不再声称每次新启动都重新验证那些未使用副本。

新报告仍保留相同的库路径、依赖、重建证明及当前目录文件哈希，因此兼容现有运行 profile。本附件保留元数据生产工具的原报告和精确旧源码快照，供核对不同版本；修改已被证据引用的源码时，也需先保存原始字节并更新历史索引。九项独立文件树夹具测试覆盖当前文件篡改、首次整理时祖先输入篡改、缺失当前清单、错误祖先报告、越界链接、循环、已有输出保护及原始 overlay 的历史命名。

另外对实际阶段独立核对了所选文件字节、路径、依赖和历史哈希保存情况。整理前后运行相同原版 actool/ibtool，实际库搜索环境完全相同，两份工具的失败日志分别逐字节一致，均报告 CallsXPC 缺失。观察到的搜索路径只包含所选目录，不包含被移出的祖先副本。随后加入 CallsXPC 及其余依赖，完整原版 workspace 也复现了新的实际错误。没有把失败改写为成功。

同一对实验的文件创建时间显示，profile 准备约由 57 秒变为 18 秒；记录方法有一秒精度，且未控制文件缓存，只是本机观察值，不是严格性能基准。确定的变化是启动输入不再包含上述约 22 GB 的旧目录副本，当前库和其他有效输入仍需校验。

## 开发者使用

需要完整开发工作区及自行提供的锁定 Intel cache/提取件、Xcode/SDK、Darling 和 LLVM。payload 相对于工作区；合并清单时保留其他 target，并为自己的实验选择新名字。reference/summary 是本地大报告的摘要，不能直接作为运行阶段配置使用。

```bash
python3 scripts/compact-resource-stage-inputs.py \
  --stage artifacts/my-graphics-stage.json \
  --output artifacts/my-graphics-runtime-inputs.json
python3 scripts/compact-resource-stage-inputs.py \
  --stage artifacts/my-resource-overlay-stage.json \
  --output artifacts/my-resource-overlay-runtime-inputs.json
python3 scripts/test-resource-stage-input-compaction.py
```

开发者配置可以选择这两份新报告及其 SHA，原来的 xcodebuild 命令和工程保持不变。继续扩展新阶段后，应再次整理新报告；不覆盖已映射库、已存在的报告或旧证据。首次整理仍要求来源输入可核验，不能利用该工具跳过缺失输入或修复失败的二进制。

本地最终选择 graphics v127 / callhistory-closure-v1 的完整运行输入报告，配置为 direct-resource-tool-environment-v79.json。所有原生命令串行并清除 DISPLAY、WAYLAND_DISPLAY、XAUTHORITY，不启动图形界面。日志以 JSON text 保存原始 UTF-8 字节，original-file-map.json 提供 SHA；源码历史保留实际版本。公开包不含 Apple/Unity 二进制、SDK、cache、XIP、证书或私钥。先前完整工程的启动超时证据仍保留，其原因没有被本轮改动证明修复。
