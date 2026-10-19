# 原版资源映像候选的准备与依赖推进

这批开发附件提供严格的候选准备、原始导出审计和独立失败证据汇总工具。它沿用苹果原版 actool/ibtool，不生成固定成功结果。完整 Unity/UE App 和真实资源编译仍未完成，安装器的固定候选没有提升。

## 准备新依赖

在此前完整研究基线上审阅合并 payload，保留本地旧文件与证据。仍需要锁定的 Intel 系统共享缓存、提取库、DyldExtractor、Capstone、Darling/Xcode 候选；Xcode XIP 不包含额外的系统框架参考输入，本附件也不包含这些二进制。路径与版本要求沿用前序附件，不是干净机器的一键恢复入口。

```bash
python3 scripts/prepare-resource-image-candidate.py \
  --image /System/Library/PrivateFrameworks/CoreTime.framework/Versions/A/CoreTime \
  --target coretime-my-experiment --build
```

工具核对原始 Intel Mach-O、固定 SHA256、实际类列表和 Swift 元数据，保存旧清单后新增 pin。目标名必须全新；不覆盖已有目标、构建目录、日志或报告。重建成功仅表示结构处理通过，不能证明框架算法或资源输出正确。

如果重建报告缺失缓存导入，先对失败候选生成只读审计，再创建另一个新目标：

```bash
python3 scripts/audit-resource-image-imports.py \
  --target my-failed-candidate --output artifacts/my-import-audit.json
python3 scripts/prepare-resource-image-candidate.py \
  --from-target my-failed-candidate \
  --exact-import-audit artifacts/my-import-audit.json \
  --target my-reviewed-candidate --build
```

审计只选取原始直接依赖中地址完全一致的唯一导出。多个不同函数共用地址时拒绝猜测。Swift `__StaticArrayStorage` 的两个导出属于同一个 Class 对象；准备器独立复核原始非执行节、isa、metaclass 导出和 class_ro 名字后才接受此已知别名。报告中的位置列表、依赖文件 SHA、选定 provider 也全部重新核验。

PoirotUDFs 和 PoirotSQLite 的原始头部空间分别比新增加载命令少 16、24 字节，初次重建被拒绝并保留。新候选显式使用 `--omit-lazy-helper-section` 省去新增 helper 节描述；helper 机器码仍在映射段中，不裁剪原始指令或越界覆盖头部。LLVM 独立解析新候选的普通/延迟绑定成功。这只处理头部布局，不证明运行语义。

重建后，用既有 `extend-coregraphics-stage.py` 向全新 stage 追加候选，生成配置并核对 stage SHA，然后串行运行 `probe-direct-resource-tools.py`。它实际启动原版绝对路径工具，清除图形会话环境，同时记录原生和外层状态；不能以版本查询替代资源编译。

## 检查与真实构建

```bash
python3 scripts/test-resource-image-preparation.py
```

六项检查在临时工作区读取真实缓存：完整导入审计的正例，以及错误原始库 SHA、导入位置、别名、provider 和依赖字节的拒绝例。失败时不能改变候选清单、历史、输出报告或构建目录。需要先保留/复现失败的 Rapport 第一版导入记录；payload 中的原始审计供复核，不提供缓存或框架。

导出审计新脚本重算的 228 项 Rapport 记录与前一独立审计逐项一致，包括已核验的 Class 别名。此结构比较和六项检查都不代表原版资源工具通过。

本批候选与逐次原版工具失败见 `evidence.json`。最新完整 Unity/CocoaPods 命令记录在 payload/config 中，使用全新 DerivedData，保留五 target、原始 scheme、iPhoneOS/arm64 和 ad-hoc 参数。其真实返回码和缺失产物也在证据中；仍需推进真实 AFNetworking/引擎编译、资源输出、完整链接和签名，再验证 UE、开发者证书、provisioning 及 archive/export。

## 本机最新结果

12 个新增候选已逐次追加并实际启动原版工具：InternationalTextSearch、CoreDuetDaemonProtocol、Rapport、PoirotSchematizer、BiomeSync、BiomeDSL、BiomeStorage、PoirotUDFs、CoreTime、PoirotSQLite、IntelligencePlatformLibrary、CascadeSets。候选的类/导出/导入数量及逐次失败路径均在证据中。它们没有逐项通过完整框架 API 的语义验证。

完整 Unity/CocoaPods workspace 使用 `unity-ios-cocoapods-v6-build-arguments.json` 和 `unity-ios-cocoapods-v7-probe-arguments.json`，资源配置为 v26、graphics stage 为 v67。实际原生/外层均返回 65，进入五 target 依赖图和原版资源查询，最后缺 CascadeSets 依赖的 AppSupport。没有 CompileC 任务，也没有 App、UnityFramework 或 AFNetworking 最终二进制。CoreSimulator 初始化本轮继续通过，但其服务完整性和稳定性仍未证明。

本附件的历史 preparation 脚本仅为解释早先输入报告中的 SHA 保留在 `reference/preparation-source-history/`；开发时使用 payload 中的当前版本。
