# 原版资源库恢复与只读 Objective-C 元数据修正

本附件继续使用原版 actool、ibtool 和 xcodebuild。新增 12 个原版 Intel 映像候选，修正 CloudCoreInternal 独立 Mach-O 格式，并在 Darling 源码中处理 XPC 常量、Security 标识符和 Objective-C 元数据写入。完整 Unity/UE App、真实资源产物及最终签名仍未完成。默认安装器候选未提升。

## 三项源码修正

* libxpc 新增原版实际值 `NetworkUploadSize` 对应的 XPC_ACTIVITY_NETWORK_UPLOAD_SIZE。完整 40 单元重建保留 642 个旧导出及 112 个 launch 重导出，总导出为 643。独立测试核对 23 个原版键值、后端/系统库符号身份、69 项数值准则及副本隔离；旧版本缺符号作为对照。没有实现 activity 调度器。
* Security 新增 kSecAttrSharingGroup 的原版 CFString 值 `ggrp`。当前运行候选仅把同一源码编译成叶库并在既有 facade 中按名字重导出；没有宣称完整 Security 源码重建。类型、值、指针归属、复制、哈希及字典键操作通过，旧 facade 缺符号对照通过；没有实现共享钥匙串操作。
* objc4 的旧加载流程会在 dyld 已保护的 __DATA_CONST 中修正 selector，实际写入导致 SIGSEGV。源码现在查询实际 VM 区域，仅在图像元数据修正期间临时允许非执行数据写入，完成后恢复原有保护，失败则明确报错。43 单元完整构建保留全部旧导出和真实 sel_lookUpByName；旧运行时崩溃对照、新运行时只读页面修复及原本可写页面保持可写三例通过。两项 selector 指针身份、39 组方法调用及前后保护检查通过；既有 selector 并发、类枚举、方法签名/结构体返回、19 种 tagged pointer 检查通过。

对应源码保存在现有分支，无新增账户或分支：

* [darling-libxpc ecd75a2](https://github.com/kxn/darling-libxpc/commit/ecd75a2a3b56167ce11eef8a4e8e401ac3bd58a4)
* [darling-security 8e7787a](https://github.com/kxn/darling-security/commit/8e7787afee108b4fbcb8178a318de7676540f814)
* [darling-objc4 c63c5aa](https://github.com/kxn/darling-objc4/commit/c63c5aa53a259a9bfe777c5bca8aaa0c0b490e65)

作者及提交者均为 Comman Kang。各源码保留自身许可证，相关 APSL/GPL 文本位于 reference/licenses。

## 独立映像格式与依赖准备

CloudCoreInternal 的原始 __DATA_CONST 第一节不在段首。LLVM 19 的绑定校验用第一节地址计算段起点，导致它把部分实际合法绑定判为越界。独立地址审计确认 815 个指针绑定都位于映射节内。这里没有修改绑定来迎合这一计算。

准备/重建器增加四个显式可选参数：省略新增前缀 padding 节描述、保留原版 LC_UUID、标记 SG_READ_ONLY，以及将非空 LINKEDIT 指令流对齐到八字节。默认构建两项回归仍逐字节相等。最终 CloudCoreInternal 候选通过 Xcode 原版 dyld_info -validate_only；同一工具明确拒绝坏 load command 和越界绑定的两个损坏副本。格式通过不代表框架算法通过。

plan-original-resource-dependencies.py 只诊断当前搜索环境中缺少的强依赖，单列弱依赖；不修改清单，不声称验证 dyld 解析或可选 dlopen。所有候选的最终目标名、类数、导出数和 SHA 见 candidate-inventory.json。输入审计及旧 preparation 源码按 SHA 保存，历史报告不能用新源码冒充。

## 在已有研究基线上复现

需要前序研究工作区、锁定的 Intel 系统缓存及提取库、Xcode/Darling、SDK 和相应 Python/LLVM 工具。XIP 不包含额外系统框架缓存；附件不包含这些二进制，也不承诺干净机器冷启动恢复。合并 payload 前必须保存旧源码、清单及其 SHA 历史，不要覆盖旧候选。

```bash
python3 scripts/build-objc-source.py \
  --output-dir runtime/my-objc-const \
  --report artifacts/my-objc-const-build.json
python3 scripts/probe-objc-data-const.py \
  --stage artifacts/private-procfs-v11-stage.json \
  --configuration config/direct-resource-tool-environment-v39.json
python3 scripts/probe-objc-data-const-regressions.py \
  --stage artifacts/private-procfs-v11-stage.json \
  --configuration config/direct-resource-tool-environment-v40.json
```

上面测试配置锁定本次实际候选；换用自己的 build 时须更新 JSON 内路径及真实报告 SHA，不能只改标签。回归脚本保留旧测试的精确实现归属断言，仅将两处固定旧库路径适配为当前候选路径，并记录派生源码与二进制 SHA。

direct-resource-tool-runtime-profile.py 的 objc_source_build 验证完整源码构建及真实库 SHA；objc_source_scope=resource-tools 只给精确列出的资源工具选择新运行时，普通 xcodebuild/服务环境保留原路径。all 模式用于上述独立测试。普通入口全局候选的一次 UTI 前置检查停在同步 XPC/LaunchServices，服务日志同时显示缺少 NativeSandbox 和 user_local_dirname；现场及显式 SIGTERM 终止记录保留，不作为完整构建成功，也未证明是 objc4 修正引起。

Darling 探测通过 session.lock 串行运行，无图形会话要求。原版资源工具已越过实际的只读 selector 崩溃，之后缺 CoreFollowUp；该库随后恢复到全新 graphics v92。后续完整 workspace 的实际状态见 evidence.json。加载、格式、常量及小程序检查不能替代真实资源编译、引擎完整链接、证书/provisioning 或 archive/export 验证。

最新完整 workspace 使用 private v11 / graphics v92 / direct-resource v41，通过 UTI 前置检查和五 target 图，原生与外层返回 65；FamilyCircle 缺 FTClientServices。新 DerivedData 没有 CompileC 任务，也没有 App、UnityFramework 或 AFNetworking 最终二进制。
