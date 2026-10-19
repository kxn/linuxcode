# 原版 AuthKit / Security、TLS 与类别方法表

本研究恢复八个原版 Intel 映像候选：AuthKit、AppleIDAuthSupport、KeychainCircle、Security、MessageSecurity、AppleFSCompression、URLFormatting、OSEligibility。八个最终候选的可执行节均与原版字节一致；修复的是独立加载所需的导入、重定位和运行时元数据，没有重新编写这些框架的业务算法。来源 SHA、候选 SHA、范围和实际工具结果见 candidate-inventory.json 与 evidence.json。

## 原始类型与单一类身份

原有环境缺少 AuthKit 的 AKAuthenticationDSIDKey，并缺少 KeychainCircle 引用的 OTControlArguments。恢复原版 AuthKit 和 Security，分别保留 214、103 个原始 Objective-C 类；AuthKit 的 32 个已知调用方导入全部存在，14 项字符串常量按原始对象和实际内容核对。

早期 libDarlingSecuritySessionValues 提供的五个类与原版 Security 重复。新的资源专用覆盖在该库安装名下仅转导出原版的五个类及其元类，不注册重复实现，也不转导出整个 Security 命名空间。实际进程通过 dlsym / dladdr 核对十个地址与原版 Security 完全相同。正常签名环境仍需独立验证；此资源配置不代表全部 Security 或认证服务已经实现。

```bash
python3 scripts/stage-original-resource-security.py \
  --target security-resource-original-patch-got-v3 \
  --inspection artifacts/security-original-patch-got-v3-inspection-v1.json \
  --reexport-session-types --tag my-reviewed-stage
```

生成的转导出映像仅有隐藏的布局填充数据和具名导出边，没有替代认证函数或 Objective-C 类。最初头部空间不足的尝试保留在 reference/security-resource-original-v2-failed-stage.json；新版本显式预留加载命令空间，不覆盖旧 stage。

## 缓存 TLS 与磁盘 TLS 的 ABI

苹果开源 dyld 的 cache builder 会把 TLV_Thunkv2 入口改成 __tlv_bootstrap+8，并把后续数据编码为 32 位 key、32 位 offset、相对模板位置与大小。Darling 的磁盘 ABI 需要普通 bootstrap、独立 key 与 64 位 offset。只给原始 patch 记录加八字节并不能恢复这个 ABI。

cache-tlv-optimization.py 只接受原始 libdyld 的明确导出身份、完整且对齐的 S_THREAD_LOCAL_VARIABLES 描述符、零 patch flags，以及与原始 TLS 模板严格相符的范围、长度与 delta。通过独立列表保存已验证的缓存转换，随后要求 TLS 恢复器实际消费每个描述符并输出磁盘布局；普通绑定和原始 GOT 校验仍保持严格。

独立检查器回读原始缓存字节，重新核对节边界、模板字段、bootstrap 绑定、零 key、变量 offset 和不存在的多余 rebase。实际副本的代码、序列化 GOT 符号名、TLS key 或 offset 被改坏，以及缺少原始缓存证明时均拒绝。

原生 probe 直接加载所选原版 Security。四个同时存活的线程对它的两个真实 TLS 描述符完成 2048 次访问，验证地址稳定、同一模板内的 offset、线程间隔离与 64 字节零初始化；不改写 Security 私有 TLS 内容，不调用认证 API。十项类身份核对和原生/外层零状态也同时通过。

```bash
python3 scripts/test-cache-tlv-optimization.py
python3 scripts/probe-original-security-tlv.py \
  --stage artifacts/private-procfs-v11-stage.json \
  --configuration config/direct-resource-tool-environment-v54.json \
  --target security-resource-original-patch-got-v3
```

## 仅含类别的 URLFormatting

在加载原版 Security 后，旧 URLFormatting 触发 NSURL 方法的选择器一致性断言。只读盘点发现它是当前范围中唯一仍保留缓存小型类别方法表的映像：没有自定义类，但有四张类别方法表。恢复其 26 个方法的普通磁盘表示，逐项核对原始 selector 和类型编码，代码字节不变。

原生对照保留：旧方法表导致 134，新候选使相同 Security TLS probe 返回原生/外层 0。没有移除运行时断言、跳过方法或改写业务代码。OSEligibility 则是 FamilyCircle 实际使用的弱依赖，必须提供真实 Swift 类型描述符；不能用空框架替代。

OSEligibility 的独立结构解析通过，但 LLVM 19 对第一节起点的偏移计算仍报告错误。新候选保留原 UUID、原始只读 DATA_CONST 语义并对齐 LINKEDIT 流；原版 Xcode dyld_info 接受该候选，并拒绝损坏头部和绑定段的两个副本。先前缺少 SG_READ_ONLY 的拒绝记录也保留，不能把该拒绝当成 LLVM 限制绕过。

## 并发候选准备

两个重叠的准备命令曾导致其中一个新 pin 丢失。其输入报告和库仍在本地；使用已保存的前一版清单与该 pin 重建出完全匹配原 SHA 的中间清单，再恢复两个记录，没有删除失败或成功的尝试。

准备器现用主机文件锁覆盖整个读取、校验、历史保存和发布事务，随后释放锁再执行只读重建。原子 rename 负责读者一致性，文件锁负责多个写者。隔离测试让两个进程的读取窗口重叠：新实现保留两个目标和准确中间历史；保存的无锁版本在同一对照下失败。

```bash
python3 scripts/test-concurrent-resource-preparation.py
python3 scripts/test-cache-patch-metadata.py
python3 scripts/test-preserved-patch-got-inspector.py
python3 scripts/test-resource-image-preparation.py
python3 scripts/test-reexport-resource-preparation.py
```

本轮六组结构/准备测试共 41 项通过；实际原版库的损坏副本另有独立控制。历史源码位于 reference/source-history；恢复旧版并发负例时，按对应 input 报告的 preparation_source_sha256 将文件复制到 runtime/source-input-history/<sha>。并发测试还需要 artifacts/messagesecurity-patch-got-v3-input.json，可从 reference/inputs 同名目标摘要恢复；C++ 转导出审计沿用前一检查点的 artifacts/libsessionutility-original-reexport-audit-v2.json。

## 复现边界

payload 相对于完整开发工作区，需与前序研究基线审阅合并，并保存源文件 SHA 历史。reference 保存准备输入、结构检查、原生结果、已保留失败和完整本地报告的 SHA；完整重建报告保留在 runtime/rebuilt-*/reconstruction.json。不要覆盖已有文件、stage、Mapped 库或日志。

仍需本地锁定的 Intel OS 缓存与提取映像、Xcode/SDK、Darling 和 LLVM。Xcode XIP 不包含额外 OS 缓存；此附件不是干净机器的一键安装包。公开内容只有源码、文档和元数据，不包含 Apple/Unity 二进制、SDK、缓存、XIP、证书或私钥。

会话串行、无图形界面。资源工具和工程均继续使用原版命令。版本查询、类型加载和 TLS 测试不等于实际资源编译或最终 App；完整 Unity/UE 链接签名、产物正确性、开发者身份/provisioning 和 archive/export 仍须验证。默认安装候选没有提升。

最终完整 workspace 使用全新 v14 DerivedData 和 private v11 / graphics v105 / direct-resource v55。UTI、五 target 图及原版资源版本查询均被实际观察；SystemAdministration 所需的 LocalAuthentication LAUserStore 缺失，原版 xcodebuild 返回原生/外层 65。未出现 CompileC 或最终 uEmuera、UnityFramework、AFNetworking 二进制。下一步继续恢复 LocalAuthentication，不将本轮标记为完整 App 编译成功。
