# 原版 NEWLAPACK 数值实现与无代码转发框架

纯 Linux x86_64 / Darling，无界面。选用 direct-resource-tool-environment-v102.json、graphics v149 与 newlapack-blas overlay；原版 Xcode 工具、Unity/CocoaPods 工程和 CI 命令保持不变。

## 原版实现与实际数值结果

恢复原版 libLAPACK、libBLAS、Accelerate 与 vecLib。两个数学库共核验 582 个 GOT 单元和 593 个绑定，可执行节字节保持一致。LAPACK 首次重建缺少的 scalbn 导入，由原版跳转桩、GOT patch 记录和 libSystem 重导出链核实，没有按折叠地址猜名称。没有将 NEWLAPACK 别名到旧接口，也没有重写 SVD 算法。

实际 SDK 头文件默认使用四字节 __LAPACK_int，并将 dgesvd_ 编译为 dgesvd$NEWLAPACK；ILP64 是另一套符号。原生测试通过 12 个矩阵、638 项检查，包括工作区查询、整数与缓冲边界、已知奇异值、零矩阵、秩亏、矩形矩阵、正交性及重建残差，包含 1e100 与 1e-100 缩放。最大缩放后相对 Frobenius 残差约 7.32e-16。通过 Accelerate 句柄查得的函数与直接调用指针一致，实际提供者为新恢复的 libLAPACK。旧配置对照重现真实的缺失符号。

初次执行进入 DGESVD 后发现 BLAS 的 NEWLAPACK 接口也缺失，失败记录保留；恢复原版 BLAS 后通过上述数值检查。旧 CPU 探针对框架目录的两个计数条件及两个 vImage 提供者路径作了精确迁移，所有数值断言保留。当前 vImage 与旧探针引用的是同一份原版映像。原版 vDSP 的 306 组步长/长度测试、BNNS 选项与 vImage 往返转换均通过；此前因旧路径断言失败的探针也保留。该覆盖不代表全部 Accelerate API 已兼容。

## 转发框架与目录

Accelerate 和 vecLib 只有头部、空 text 标记、零符号/零导出及原版重导出命令，没有函数体。检查器支持这份实际结构，严格验证零填充、符号侧表、空节地址以及 vecLib 的 LC_SUB_CLIENT；保留原始 UUID、依赖、版本命令和允许的客户端。两个框架共十一项重导出。四个原版格式正例、八个格式损坏对照通过；两个新转发框架另有 21 项实际候选损坏被拒绝，原有 AVFoundation/ApplicationServices 的十五项损坏回归也通过。

嵌入的 libLAPACK/libBLAS 保留原始框架目录，并仅将显式选中库所在目录加入子进程库搜索路径。整个 Accelerate 树从新阶段复制，不覆盖已映射库。旧 v100 配置的工具环境与此前真实探针逐项一致。当前运行输入仍经过哈希与目录检查。

## 完整工程结果与复现

原版 actool/ibtool 和完整 Unity/CocoaPods workspace 已越过 NEWLAPACK，当前停在 DVTSmartSearch 需要的 Swift NaturalLanguage enumerateNeighbors 接口。原版 overlay 中已确认该真实导出，尚未恢复并执行。完整 workspace 进入五 target 依赖图，UTI 预检通过，原版 xcodebuild 和外层进程正常返回 65。CompileC 为零，uEmuera、UnityFramework 和 AFNetworking 最终二进制仍不存在。

资源编译、完整 Unity/UE App 链接和签名、证书签名及 archive/export 尚未完成；默认安装候选没有提升。历史启动超时根因也未证明修复。

需要完整本地开发工作区、用户自行提供的锁定 Intel cache/提取件、Xcode/SDK、Darling 与 LLVM。公开附件只包含源码、配置和文字证据，不含 Apple/Unity 二进制、SDK、cache、XIP、证书或私钥；XIP 不包含全部系统框架。payload 相对开发工作区；合并 pins 和历史 revisions 时保留已有 target 和开发者修改。reference/summary 为大报告摘要，不能作为运行输入。

```bash
python3 scripts/probe-original-newlapack-svd.py \
  --configuration config/direct-resource-tool-environment-v102.json \
  --baseline-probe runtime/direct-resource-tools-79ga4vse/result.json \
  --stage artifacts/private-procfs-v11-stage.json
python3 scripts/probe-direct-resource-tools.py \
  --stage artifacts/private-procfs-v11-stage.json \
  --configuration config/direct-resource-tool-environment-v102.json
```

首项应通过数值和 CPU 回归，第二项目前应失败于 Swift NaturalLanguage。完整工程参数为 unity-ios-cocoapods-v59-probe-arguments.json；重跑时换用新 DerivedData。所有原生命令串行执行，清除 DISPLAY、WAYLAND_DISPLAY、XAUTHORITY，使用新阶段/日志/报告名。reference/original-file-map.json 保存路径与 SHA，日志及历史源码使用 UTF-8 JSON text 封装。实际进度见 reference/artifacts/newlapack-resource-progress-v2.json。
