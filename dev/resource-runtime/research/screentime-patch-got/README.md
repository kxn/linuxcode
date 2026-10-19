# ScreenTime 依赖恢复与 Swift 原指令保留

本批恢复 33 个原版 Intel 映像候选，并提供可复用的依赖准备、批量 staging 和精确元数据检查。原版 actool/ibtool 已越过此前的 FTClientServices、StorageContainersPrivate 和 ScreenTimeCore 依赖组，下一处缺失库为 TelephonyUtilities 引入的 CallKit。完整 Unity/UE App 与资源编译尚未通过，默认安装候选未提升。

## 两个 Swift 模块的具体修复

AppleMediaServices 的初次重建中，线性反汇编把部分内联数据当作指令；原始指针还包含非零重定位加数、重导出后的名称和指向共享 GOT 槽位的地址。未知项没有被填成空值并输出为库，失败候选保留在本地报告中。

现在使用既有 v4 dyld patch 表恢复模式，并明确扩展到同时完成 typed Swift 相对元数据修复的候选。准备器固定原始表 SHA、单元数与范围；没有选择离目标地址最近的符号。AppleMediaServices 最终恢复 2,241 个 GOT 绑定、50 个非零加数和 7 处槽位地址引用，两个原始可执行节共约 8 MB，独立逐字节比较一致。AppleMediaServicesKitInternal 恢复 979 个池中 GOT 绑定及 5 个自身 __got 槽位，同样未改写原始可执行节。

重导出匹配是显式可选行为。只有原版导出链确实将原导入名重导出为 patch 表中的名字，才接受该身份。例如 CoreGraphics 的 CGDisplay 名称重导出为 SkyLight 的 SL 名称，libc 的 memcmp/memmove 名称重导出为平台实现。两个公共名称都指向同一 canonical 函数时，只在原始依赖中找到唯一实际 canonical 导出的情况下使用该导出；不随机选择一个公共名称。相同地址但缺少导出链的不同函数依旧拒绝。

指向 GOT 的地址恢复为独立映像中同一 VM 偏移的槽位地址，不把它误当作槽位存放的函数值。独立检查器同时解析实际 rebase/bind 指令流及文件中的目标指针。自身 __got 只接受实际原始槽位、真实 symbol stub 引用，以及已经恢复的绑定或图像内重定位。未覆盖槽位仍拒绝输出。

AppleMediaServicesKitInternal 的头部空间不足，最终候选显式省去新增 padding/helper 节描述、保留原版 UUID、保护 DATA_CONST 并对齐 LINKEDIT 流。Xcode 原版 dyld_info 在 Darling 中接受此候选，同时拒绝两个损坏副本。LLVM 对两个最终候选的绑定表解析也通过。以上都是格式和序列化检查，不等于框架所有算法经过验证。

## 数据别名与 CoreLocation

MediaServices 所引用的两个 SonicFoundation Swift 元数据导出被原版缓存合并在同一个只读对象。这里同时检查原始导出、原始非执行常量节、所选原版 SonicFoundation 候选的两个实际导出地址、VM 偏移与常量内容，才允许这一个已知别名对。没有复制一个猜测的描述符或放宽函数别名规则。错误地址、错误名称和改变的候选常量三个对照均被拒绝；完整运行时行为仍未由此证明。

为此恢复了原版 SonicFoundation 和 libswift_DarwinFoundation3。原版 CoreLocation 也进入独立资源工具作用域；原先 Darwin/CoreLocation 与原版 _LocationEssentials 共同定义 CLLocation 的警告在本轮两份工具日志中不再出现。没有宣称定位服务、GPS 或全部 CoreLocation API 通过。

## 开发工具与边界

plan-original-resource-dependencies.py 支持 --target-manifest，核对不同候选清单中的原始 SHA，诊断当前环境中缺少的强依赖；弱依赖另列，路径存在不代表 API 完整。依赖组与每次失败保留在 reference 中。

prepare-resource-dependency-batch.py 按明确列出的配置串行准备，保留每次失败。遇到无法按原始依赖精确核对的导入时停止，不跳过。existing_target 仅用于复用基线中实际已有且 SHA 正确的成功候选；干净目录不能照搬这类路径当作已完成构建。

extend-coregraphics-stage.py 可以重复传 --target，一次核对整组候选后构造全新目录，避免为每个库复制一次完整环境。包含错误第二个目标的对照确认没有创建输出。旧候选、库、源文件及报告不被覆盖。

```bash
python3 scripts/prepare-resource-image-candidate.py \
  --from-target applemediaservices-resource-v1 \
  --exact-import-audit artifacts/applemediaservices-original-import-audit-v1.json \
  --verified-subset-import-audit \
  --preserve-code-with-patch-got --patch-got-renamed-reexports \
  --target applemediaservices-my-reviewed-experiment --build
```

verified-subset-import-audit 只接纳再次核对过的 selected 行，未解析行仍不绑定；重建器必须通过独立的 patch/typed 元数据恢复解决它们，否则拒绝输出。默认模式仍要求完整审计全部解析。

```bash
python3 scripts/inspect-preserved-patch-got.py \
  --target applemediaservices-patch-got-v5 --output artifacts/my-new-inspection.json
python3 scripts/test-preserved-patch-got-binaries.py \
  --target applemediaservices-patch-got-v5 \
  --target applemediaserviceskitinternal-patch-got-v5 \
  --output artifacts/my-new-corruption-controls.json
python3 scripts/test-cache-patch-metadata.py
python3 scripts/test-preserved-patch-got-inspector.py
python3 scripts/test-resource-image-preparation.py
```

15 项 patch 表检查、4 项检查器检查、6 项准备器检查通过。两个真实候选的内存副本中，改变代码、GOT 地址引用或本地绑定证明分别被拒绝；没有修改候选文件。新控制报告和实际候选检查在 reference 中。

需要既有研究基线、锁定的 Intel 缓存/提取库、SDK、Xcode、Darling 和 LLVM 工具；本附件不是干净机器的一键恢复包。payload 路径按工作区原路径保存，合并前需按 SHA 保存旧源码与清单历史。source history 保留实际输入报告所引用的 preparation 源码。本附件只包含源码、文档及元数据，不包含 Apple/Unity 二进制、缓存、SDK、XIP、证书或私钥。

最终候选为 private v11 / graphics v95 / direct-resource v44；完整 workspace 的实际结果见 evidence.json。资源工具通过精确路径作用域选择这组库及此前的 ObjC 修正；普通构建服务继续使用已验证的原运行时路径。Darling 会话串行运行且无图形会话要求。完整 App 链接签名、UE、证书/provisioning、archive/export 和资源产物正确性仍需继续验证。

本轮完整 workspace 使用全新 v10 DerivedData，UTI 前置检查和五 target 依赖图通过，原生与外层均返回 65，失败为 TelephonyUtilities 缺 CallKit。没有 CompileC 任务，也没有 App、UnityFramework 或 AFNetworking 最终二进制。
