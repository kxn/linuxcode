# Telephony 依赖、原始弱引用与 KeyPath 环境

这批研究恢复 26 个原版 Intel 映像候选。原版 actool/ibtool 已越过 CallKit 和 TelephonyUtilities 的这组依赖，下一处缺少 CMCapture 引入的 CMCaptureCore。完整 Unity/UE App 与资源产物尚未通过；默认安装候选没有提升。

## 原始弱引用缺库语义

TokenGeneration 和 AppleIntelligenceReporting 分别有 16、4 个符号引用 IntelligencePlatformLibrary_AppleInternal。原始加载命令是 LC_LOAD_WEAK_DYLIB，全部符号是 undefined + N_WEAK_REF，n_value 为零；该提供库既不在原始缓存中，也没有提取文件。

新 absent-weak-imports.py 从实际 Mach-O 独立核对这些条件。只有显式 --allow-absent-weak-dependencies 才固定此原始缺库条件；有强符号、非零符号、已存在的提供库或声明不一致均拒绝。重建保留原始弱加载命令，不创建 AppleInternal 框架，也不实现或假装调用这些 API。staging 还检查提供库没有出现在所选环境及基础根中，避免把不同安装条件套用为同一个候选。

独立原生矩阵在 Darling 中实际执行：缺库的弱引用为 NULL；提供库存在时调用真实函数并得到 83；同样缺库的强链接在进入 main 前失败。两种成功情况必须同时得到原生零状态和实际程序标记。强依赖失败时 dyld 可以在 shell 状态标记输出前终止会话，负例据真实非零外层状态、缺库错误及未进入 main 判定，早先过严的判定及原始日志保留。

AppleIntelligenceReporting 的两个共享 GOT 槽位在原始缓存中本来就是全零。候选保留其 VM 偏移与空值，没有添加绑定或重定位。检查器必须回读实际缓存，核对原版 symbol stub 指向该槽位、候选值为零，以及不存在多余 bind/rebase。改变候选空槽位或缺少原缓存证据都会被拒绝。它不代表实现了任何缺失框架 API。

## 显式 KeyPath 环境

GenerativeFunctionsFoundation 的一处未命名二进制泛型环境曾被扫描成 symbolic type 字符串。只读反向引用分析找到一个完整有效的 KeyPath pattern，随后核对其原始 __TEXT,__const 范围、泛型环境、带标记的 root/leaf type、buffer extent 和 component kind。重建仅使用显式固定且再次验证的 pattern，不以任意字节特征跳过区域。

```bash
python3 scripts/prepare-resource-image-candidate.py \
  --image /System/Library/PrivateFrameworks/GenerativeFunctionsFoundation.framework/Versions/A/GenerativeFunctionsFoundation \
  --swift-keypath-pattern 0x7ffc154160f8 \
  --target my-keypath-reviewed-candidate --build
```

地址仅适用于本次 SHA 固定的原始输入，不能直接套到其他 SDK。原始泛型头和四个要求均保留。错误环境地址、去除 root 标记、保留 buffer 标志和重复 pattern 四个对照被拒绝；本检查不证明全部运行时 KeyPath 投影。

## 保留原指令与独立解析

四个候选使用此前的原指令保留/patch-GOT 模式：GenerativeModels、GenerativeModelsFoundation、GenerativeFunctionsFoundation、AppleIntelligenceReporting。独立检查同时核对实际可执行节字节、序列化绑定、GOT 地址引用、本地槽位及原始空槽位。实际二进制的内存副本损坏后必须被拒绝，不修改原候选文件。

后两个候选再次触发 LLVM 19 把第一节地址当作段起点的限制。没有为了迁就这一计算而改写原始合法偏移。检查器只在以下条件全部满足时记录这个特定限制：独立解析的实际 LC_SEGMENT/section 边界合法；能重现第一节起点假设造成的冲突；错误确为该 offset 错误；同一字节 SHA 的候选已被原版 Xcode dyld_info 接受且两个损坏副本被拒绝。原工具字节须与 XIP 提取文件一致，错误图像 SHA 或损坏对照的伪证明均拒绝。

```bash
python3 scripts/inspect-preserved-patch-got.py \
  --target generativefunctionsfoundation-patch-got-v4 \
  --output artifacts/my-new-inspection.json \
  --original-validator-report runtime/original-dyld-validation-yaorailv/result.json
```

原版校验报告也绑定本次实际工作区与输入；换环境必须重新运行 probe-original-dyld-validation.py。格式和字节检查不代表所有框架算法已验证。

## 批量准备与复现边界

prepare-resource-dependency-batch.py 新增 --keep-going，只用于收集独立失败。缺失项仍不算成功，批次 complete=false 且退出非零；错误后面的有效目标仍会核对。实际负例确认候选清单和源码历史没有改变。默认行为仍是首个未知问题即停止。最终 staging 仅接受全部已成功并且 SHA 正确的候选。

```bash
python3 scripts/test-absent-weak-imports.py
python3 scripts/probe-absent-weak-runtime.py --stage artifacts/private-procfs-v11-stage.json
python3 scripts/test-cache-patch-metadata.py
python3 scripts/test-preserved-patch-got-inspector.py
python3 scripts/test-resource-image-preparation.py
```

六项弱引用结构检查、原生三场景矩阵、15 项 patch 表检查、4 项检查器检查、6 项准备器检查及真实二进制损坏控制通过。具体原始输入、每次保留的失败、最终候选数量、来源 SHA 和实际 workspace 结果位于 candidate-inventory.json、reference 与 evidence.json。

最终研究配置为 private v11 / graphics v96 / direct-resource v45。仍需要前序完整研究基线、锁定的 Intel 缓存与提取库、Xcode/SDK、Darling 和 LLVM；本附件不是干净机器的一键恢复入口。合并 payload 前需保存原文件和 SHA 历史，不覆盖已有候选、日志或报告。附件仅含源码、文档和元数据，没有 Apple/Unity 二进制、SDK、缓存、XIP、证书或私钥。

Darling 会话串行、无图形会话要求。原版工具与项目保持原流程；当前完整 App 编译、资源产物正确性、Unity/UE 链接签名、证书/provisioning 及 archive/export 仍未完成。

本轮完整 workspace 使用全新 v11 DerivedData，UTI 前置检查和五 target 图通过，原生/外层均返回 65，失败为 CMCapture 缺 CMCaptureCore；没有 CompileC 或最终 App、UnityFramework、AFNetworking 二进制。
