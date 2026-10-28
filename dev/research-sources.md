# 找到、核验和审阅较新的研究源码

`linuxcode-dev checkout` 仍锁定较早的 `375e52e` 开发基线，固定的 `apply-overlay.py` 也只应用其声明的资源更新。它们不会自动组合后续 stage104/106、Unity 成功候选或最新 UE 修复。后续源码已随本仓库及默认公开 source 包保留，可以先独立核验和导出，审阅后再合并到自己的固定源码工作区；这一步不安装运行时，不需要启动 Darling。

在整合仓库或解开的 source 包根目录运行：

```bash
python3 dev/research-sources.py list --match host-vm
python3 dev/research-sources.py list --match xnu-wait
python3 dev/research-sources.py list --match s2c
python3 dev/research-sources.py list --match unreal
python3 dev/research-sources.py list --match unity
python3 dev/research-sources.py inspect xnu-wait-atomic-suspension-handoff \
  --workspace /path/to/linuxcode-workspace
```

工具通过 `overlay.json` 的 SHA256 核验随包的显式 `*-package.json`、README 和声明的 payload。`inspect` 显示每个目标文件是相同、不同、缺失，还是需要人工处理的符号链接，并列出可用的证据附件。列表只覆盖带显式打包 spec 的研究包；其他早期材料仍可从[开发说明](README.md)和[资源研究文档](resource-runtime/README.md)进入。包名是历史检查点，不能按名称或 stage 数字推断可以依次自动覆盖。

默认小型 source 包保留 payload、spec 和 README，省略 `reference/` 历史附件。因此 `historical_evidence_complete: false` 可以是预期结果，不表示源码 SHA 错误，也不表示历史测试通过。需要完整公开 JSON、原始文件映射和历史源码摘要时，在整合仓库使用 `python3 linuxcode.py package --output /path/to/new-source.tar.gz --include-research-history`。这仍不包含私有运行时、Apple/Epic 工具或签名材料。

| 需求 | 包名与实际范围 |
| --- | --- |
| stage104 VM 统计 | [host-vm-statistics-upstream-interface](resource-runtime/research/host-vm-statistics-upstream-interface/README.md)：补齐上游现有 Mach host 接口的真实 Linux 测量；原分发与缓存保留，不能视为完整 Darwin VM 记账或 UE 构建完成 |
| stage106 原子等待交接 | [xnu-wait-atomic-suspension-handoff](resource-runtime/research/xnu-wait-atomic-suspension-handoff/README.md)：复用现有 XNU 锁和“挂起时释放锁”接口；八项 Linux C/C++ 回归和真实 actool 查询通过；被拒绝的 stage105 不是升级步骤 |
| 后续活线程 S2C 中断修复 | [s2c-interrupted-reply-transaction](resource-runtime/research/s2c-interrupted-reply-transaction/README.md)：复用既有 perform 信号量，在活线程的 reply wait 被中断时保持事务所有权；五项宿主回归通过、旧源码负对照复现故障；死亡/exec 和完整 UE 构建仍待验证 |
| 原版 UE workspace 和 CocoaPods | [unreal-cocoapods-workspace-integration](resource-runtime/research/unreal-cocoapods-workspace-integration/README.md)：原 workspace 引用选择、跨工程依赖、UE/Pods 配置 wrapper、首次基线与同 OFD 会话锁；native 安装和配置检查通过，不能单独证明 Pod 编译或 UBT 链接 |
| UE workspace 内的真实 Pod 归档 | [unreal-real-pod-archive](resource-runtime/research/unreal-real-pod-archive/README.md)：原版 Xcode 生成 arm64 LocalMath archive，独立 LLVM 确认 `_local_add`；这是证据包，没有额外 payload；后续 server 故障使该次完整 UE 构建未完成 |
| 原版 Unity 完整链路 | [unity-fresh-linux-certificate-end-to-end](resource-runtime/research/unity-fresh-linux-certificate-end-to-end/README.md)：Linux Unity 新项目导出、原 CocoaPods、空 DerivedData 的原 Xcode 构建、测试证书签名和独立检查；使用冻结的 stage101/config154 候选，不等于 stage106 完整回归 |
| Unity Release 归档 | [stage101-fresh-unity-release-archive](resource-runtime/research/stage101-fresh-unity-release-archive/README.md)：同一已具备运行环境中的真实 xcarchive、严格签名和 DWARF/UUID 检查；设备安装和 Apple 开发者 provisioning 仍未证明 |

例如，导出 stage106 源码到全新审阅目录：

```bash
python3 dev/research-sources.py export xnu-wait-atomic-suspension-handoff \
  --workspace /path/to/linuxcode-workspace \
  --output /path/to/linuxcode-workspace/runtime/review-stage106
```

导出只写指定的新目录和其中的 `.linuxcode-research-export.json`，保留每项源码路径和 SHA，不改原 workspace 的文件、Git 索引或默认运行选择。不同内容必须审阅；工具拒绝向已存在目录或所选工作区的 `vendor/` 导出。它不拼装多个研究包、不自动应用补丁、不构建或运行任何脚本。证据包可以 `inspect`，不能当作源码包导出。

先在各组件仓库核对自己的 base HEAD、现有修改及研究包的发布 commit，再比较所需差异：

```bash
git -C /path/to/linuxcode-workspace/vendor/darlingserver status --short
git -C /path/to/linuxcode-workspace/vendor/darlingserver rev-parse HEAD
diff -u /path/to/linuxcode-workspace/vendor/darlingserver/duct-tape/src/thread.c \
  /path/to/linuxcode-workspace/runtime/review-stage106/vendor/darlingserver/duct-tape/src/thread.c
```

`diff` 返回 1 表示存在差异。研究 payload 包含该检查点的完整文件，可能同时带有更早的相关修改；不能用整文件覆盖来代替合并审查。优先复用当前上游或既有实现，保留自己的变更；只有确认需要的差异后，才在自己的组件仓库合并、独立构建并执行最相关回归。若采用研究包 README 记录的 fork commit，同样要核对其父版本和额外差异；旧开发工具的 HEAD 校验不会因此自动升级。

`export` 成功只表示所选公开源码可读取、SHA 匹配并已复制供审阅。stage104/106 的原生 probes、UE/Unity 原版工具证据和自己的重新构建结果应分别保存。RPC/MIG 生成输入、server 与客户端 ABI、系统库和资源候选必须一致；不能把别处的 `artifacts/*.json` 当作二进制或配套运行环境已经存在。完整候选仍依赖私有 Intel OS 参考输入和未完全自动化的重建顺序，XIP 加这些 source 包尚不足以实现全新 Linux 的完整冷启动。
