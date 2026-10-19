# Unity 原版宿主平台识别与稀疏文件复制

本附件补全纯 Linux x86_64 / Darling 环境中的两项实际兼容问题。Unity 原版程序集、原版 Bee/IL2CPP、Xcode 工程及其 PBX 脚本保持原样，执行入口仍为苹果原版 xcodebuild。

## 客体文件系统布局

原版 Bee 通过 `Directory.Exists("/proc")` 判断 Linux。Darling 原先把后端 procfs 挂在客体 `/proc`，使原版 iOS 工具链拒绝运行。新候选把 namespace 内的 procfs 挂到 `/private/var/db/darling/proc`，同时迁移使用 Darwin 路径解析的内部调用者。Linux 原生后端继续使用自己的 `/proc`。

该路径由 Darling 的 `darling-config.h.in` 定义。server 挂载、完整 libsystem_kernel、完整 libSystem/libkqueue 以及运行根布局必须一起更新。不要使用 `/var/run` 作为挂载点：Darling preinit 会清理该目录。HIServices 的源码调用者也已迁移，但当前所选原版框架候选没有使用重建的 HIServices，不能把它算作运行验证通过。

已验证：

- 原版 Bee.Tools.dll 在原版 Unity CoreCLR 中实际返回 IsOSX=true、IsLinux=false、HostArchitecture=X64。
- 原生回归检查真实 namespace PID、sysctl、描述符路径、管道、EVFILT_VNODE 写入事件，以及 CLOEXEC_DEFAULT/file actions 子进程继承。
- `/dev/fd` 和内部 procfs 的绝对链接目标保持物理路径语义。vnode 监听保留 procfs 描述符路径，交给 Linux 根据实际 inode 建立监听。

## 防止“构建成功、产物全零”

第一次越过平台检查的真实 Unity 构建执行了 443 个任务。中间 GameAssembly 静态库通过独立检查，包含 246 个 arm64/iPhoneOS 对象和两个代码注册符号；但最终复制出的同等长度文件全部为零。该次 Xcode 成功横幅已被拒绝。

Darwin 的 SEEK_HOLE=3、SEEK_DATA=4；Linux 的值相反。原先 sys_lseek 直接透传，导致稀疏复制把数据区当空洞。修复只在系统调用兼容层转换这两个操作，继续使用实际文件数据与原始复制实现。

新的回归把输入同步到磁盘后取得 Linux extent oracle，避免延迟分配使先后两次查询看到不同 extent。保留了同步前探针的失败记录。当前通过 24 项边界/数据区/空洞查询，以及原版 Unity System.Native 普通复制和 copyfile 稀疏复制共 6 项逐字节核对。原版普通复制在修复前已能正常复制；修复前错误发生在稀疏复制，证据分别保留。

修复后的完整 Xcode 重跑已经成功，最终输出的三个静态库均通过独立检查：GameAssembly 246 个、IL2CPP runtime 128 个、baselib 3 个 arm64/iPhoneOS 对象，共 377 个；各自的关键符号也已核对。最终产物另按 SHA256 保存在本机，公开包只保存校验记录。原始 PBX 清理过程删除了前一次中间缓存，那次中间库的报告仍保留，但其原始字节已不可用；不能把它当作可重复核验的现存产物。

完整 Xcode 重跑及最终产物检查见 evidence.json。另一次重跑在进入编译前发生 Darling server 信号量 panic，已记录为失败；这仍是稳定性问题，不能由随后成功的单次构建证明已解决。

最终候选还通过了原版 codesign 对已有 CocoaPods smoke App 的 ad-hoc 签名、严格验证、独立页/资源/XML 与 DER entitlements 核对，以及四类篡改拒绝。该回归的 App 是已有小型工程，不能证明 Unity App 已经完成签名。

## 已有开发工作区复现

先准备完整研究基线、原版 Xcode/SDK、Unity 导出输入、参考运行库和先前的原版 plutil 候选；本附件没有包含这些二进制输入。按 reference/source-revisions.json 使用现有四个 fork 的明确提交，审阅 payload 后合并到同名路径，并按哈希保留旧报告引用的源码。

```bash
python3 scripts/build-shared-remap-server.py
python3 scripts/build-libsystem-kernel-source.py \
  --source-manifest reference/source-revisions.json \
  --output-dir runtime/private-procfs-kernel-NEW \
  --variant-base runtime/original-host-tools-PREVIOUS/darling-root \
  --report artifacts/private-procfs-kernel-NEW-build.json
python3 scripts/build-libsystem-kqueue-source.py
python3 scripts/link-libsystem-kqueue-source.py \
  --objects runtime/libsystem-kqueue-source-NEW/objects.json
python3 scripts/stage-private-procfs-runtime.py \
  --parent-stage artifacts/original-host-tools-PREVIOUS-stage.json \
  --server-build runtime/shared-remap-server-NEW/stage.json \
  --kernel-build artifacts/private-procfs-kernel-NEW-build.json \
  --libsystem-build runtime/libsystem-kqueue-source-NEW/build.json --tag NEW
python3 scripts/test-private-procfs.py --stage artifacts/private-procfs-NEW-stage.json
python3 scripts/probe-original-bee-host-platform.py --stage artifacts/private-procfs-NEW-stage.json
python3 scripts/probe-original-dotnet-copyfile.py --stage artifacts/private-procfs-NEW-stage.json
```

NEW/PREVIOUS 替换为实际构建输出和父候选。source manifest 的路径需指向本附件内实际文件。独立 server CMake 配置会根据源码模板生成 darling-config.h；kernel 和 libSystem 构建使用同一生成目录。所有 Darling 执行继续通过 session.lock 串行进行，图形环境变量被移除。

原有 Xcode 探针新增 `--private-procfs-stage artifacts/private-procfs-NEW-stage.json`，在 `--loader-environment-stage` 后选择整套候选。config 中保存真实原版 GameAssembly 子目标命令；独立的 inspect-unity-gameassembly.py 校验 archive、每个对象的 Mach-O CPU/平台及生成代码注册符号。Unity 把 runtime 实现放在另一个 il2cpp.a，GameAssembly 的符号检查据此划定范围。

此附件没有自动替换安装器默认候选。完整 Unity/UE + CocoaPods App、资源编译、开发者证书/provisioning、设备信任、archive/export、稳定性及从零重建仍需继续验证。
