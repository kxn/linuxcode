# 原版资源依赖、符号表别名与纯数据映像

纯 Linux x86_64 / Darling 的实验检查点。选入 CoreTelephony、TabularData、libAccessibility、MediaAccessibility、UIFoundation、libswiftSpatial，以及原版纯数据 libSpatial。六个含代码的映像独立核对了 2913 个 GOT 单元、13244 个绑定，可执行节字节保持一致；libSpatial 原本没有可执行代码，其 48 字节常量及两个私有版本符号保持一致。七份映像均有原版 dyld_info 格式正例及两项损坏对照。格式检查不代表框架 API 全部兼容。

原版 actool/ibtool 依次越过 CoreTelephony、TabularData、libAccessibility、MediaAccessibility、UIFoundation 和 Spatial 依赖缺失。最新两个工具均停在 source libSystem 所缺的 matrix_identity_double4x4。原版提供者的 128 字节 double 矩阵已核对，尚未补入所选运行库。

完整原版 Unity/CocoaPods workspace 在配置 v83 和 v86 各运行一次，均进入五个 target 的依赖图，UTI 预检通过，原版 xcodebuild 与外层进程均返回 65。前一次失败于 NSTextScaleAttributeName；选入 UIFoundation 及 Spatial 依赖后，后一次失败于 matrix_identity_double4x4。CompileC 为零，uEmuera、UnityFramework 和 AFNetworking 最终二进制均不存在。Unity/UE 完整 App、资源编译、证书签名及 archive/export 仍未完成，默认安装候选没有提升。历史启动超时的原因也未被本轮证明修复。

## 本轮源码修复

- inventory-runtime-dependencies.py 按 Darling dyld 的 framework 叶名称规则区分真正的框架二进制与 framework 目录内的嵌入 dylib，消除 FontParser、SessionUtility、faceCore 的错误缺失报告。四项真实 Mach-O 搜索路径测试通过。
- normalize-dysymtab-aliases.py 支持保留原版改名 N_INDR 别名的整条 nlist 记录、目标字符串和间接符号身份。UIFoundation 的四个 NS Emoji 类别名逐项核对原始导出表，均对应 CoreText 的 CT Emoji 类；没有新增类实现。九项表格测试，以及 UIFoundation、AVFAudio 各七项真实二进制篡改拒绝检查通过。
- prepare-resource-image-candidate.py 增加 constant-only-image 模式，先严格验证原版 libSpatial 的空代码节、常量节、两个私有版本符号、零导出与依赖，再跳过不存在的函数分析。original-constant-image.py 独立比较常量、节地址、符号和无操作绑定流。五项真实候选篡改控制，以及原版 dyld 对损坏头部和越界段的拒绝记录均保留。没有伪造 GOT、函数入口或成功状态。
- inventory-resource-tool-scope.py 从真实工具探测结果读取搜索路径，显式扫描暂存映像并生成静态清单。最终扫描 657 份暂存文件，追踪到 710 个映像，无扫描/解析错误；仍有一项强依赖文件缺失。这是候选集合，不是实际加载集合。符号审计检查 987368 个 classic 绑定位置，20 个含 chained fixups 的映像未审计；不据此宣称依赖闭包或 ABI 已完整。

## 开发者复现

需要完整本地开发工作区、锁定的 Intel 系统 cache/提取件、Xcode/SDK、Darling 和 LLVM。XIP 本身不足以提供本实验使用的全部系统框架。payload 相对于工作区；合并源码、pins 与源码历史时保留已有 target、revisions 和开发者修改。reference/summary 仅是本地大报告的摘要，不能直接作为运行阶段报告使用。原始文件映射和 SHA 见 reference/original-file-map.json；日志与历史源码以 JSON text 封装，解码后可核对原始 SHA。

```bash
python3 scripts/test-runtime-inventory-search-paths.py
python3 scripts/test-dysymtab-alias-normalization.py
python3 scripts/probe-original-constant-image.py \
  --target libspatial-original-data-v2 \
  --stage artifacts/private-procfs-v11-stage.json
python3 scripts/probe-direct-resource-tools.py \
  --stage artifacts/private-procfs-v11-stage.json \
  --configuration config/direct-resource-tool-environment-v86.json
```

上述原版资源工具当前应失败于 matrix_identity_double4x4。配置中间版本也保留，但只有证据列出的命令实际运行过；不能把未执行的 build/probe 参数文件当作成功测试。所有原生命令串行使用同一会话锁，清除 DISPLAY、WAYLAND_DISPLAY、XAUTHORITY。运行目录和报告采用新名字，不覆盖已映射库及失败记录。

继续开发时先补充 SDK ABI 一致的 double4x4 常量，核对原版字节、对齐及真实调用，再重跑原版资源工具和完整 Unity/UE 工程。公开附件只含源码、文档和元数据，不含 Apple/Unity 二进制、SDK、cache、XIP、证书或私钥。
