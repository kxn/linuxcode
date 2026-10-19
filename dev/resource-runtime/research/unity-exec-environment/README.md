# Unity 原版 .NET：子进程环境传递

修复 Darling 内核兼容库的 execve 临时数组生命周期，使内部 loader 变量不再变成空字符串并随子进程累积。使用原版 Unity .NET 7.0.13 的托管探针，现在能够同时读取 PATH 并从环境字典中枚举到它；修复前，单独 getenv 正常，字典却为空。

源码在原有 [darling-xnu 分支](https://github.com/kxn/darling-xnu/commit/cdad4892d5041b77917719552932de47093d0871) 保存，提交身份 Comman Kang。整合与开发附件继续在本仓库 main。**本附件不代表已经编译出 GameAssembly 或完整 Unity/UE App。**

## 原因和验证

`execve_internal` 在块内声明了 `mldr_lifetime_pipe_env[32]`，将其地址保存到 envp 后离开块，再进行服务器 checkout、信号设置及真正的 Linux execve。地址的有效期没有覆盖最终使用。优化编译中，此项以空字符串到达 mldr，loader 无法把它当作内部参数删除。

只读现场跟踪显示：原生环境仍有 PATH，但 .NET 环境块以空 UTF-16 项开头，枚举提前结束。临时诊断 loader 又确认空项在进入 mldr 时已经存在，并逐代累积，排除了将问题简单归因于“没有安装 uname”。诊断 loader 没有用于最终候选。

修复将数组移到函数作用域，保持到最后的 Linux execve。没有清理用户空字符串来掩盖问题，没有硬编码 PATH/uname，也没有改 Unity 工程或原版工具。

- 完整 879 个源码单元重建；最终隔离根使用原有 mldr、已验证共享重映射 server、完整 libSystem/libkqueue 及新内核库。
- 同一回归在旧库中因新增空环境项失败，在新库中通过：fork、posix_spawn、两条各 7 次的 exec 链、PATH、UTF-8、字面 shell 符号、合法空值、内部变量移除、调用方输入不变及真实 ENOENT。
- 原版 CoreCLR 运行自建小型托管测试程序集，修复前枚举 0 项，修复后枚举 19 项，直接 PATH 和字典 PATH 一致。随后读取子进程输出时仍触发真实 JIT RW 映射失败，**该完整探针仍记录为失败，不能称为完整托管子进程验证成功。**
- 原版 plutil 候选也已单独通过原版 codesign ad-hoc 签名、严格校验、独立签名核对、XML/DER entitlements 和四类篡改拒绝；仍不代表开发者证书或设备信任。

## 已有开发工作区复现

需要先前完整研究基线、事件注册附件、LLVM 19、原版 Xcode/SDK、现有生成 RPC/MIG 头和参考运行库。小型托管探针另需 Linux `mono-mcs`，它只编译测试程序集；执行使用 Unity 导出工程自带、未经修改的 macOS x86_64 libcoreclr.dylib，没有用 Mono 执行来代替 .NET。

将 payload 源码审阅后合并到同名路径，先按哈希保存旧报告引用的输入。在干净的 fork 检出中，kernel 构建器可通过 `--source-manifest` 指定本附件 reference/source-revisions.json，接受所记录的精确提交。完整干净重建仍未实测，固定 overlay 和安装器默认候选没有改变。

```bash
python3 scripts/build-libsystem-kernel-source.py \
  --output-dir runtime/exec-environment-kernel-NEW \
  --variant-base runtime/shared-remap-runtime-v2/darling-root \
  --report artifacts/exec-environment-kernel-NEW-build.json
python3 scripts/stage-shared-remap-runtime.py \
  --server-stage artifacts/shared-remap-runtime-v2-stage.json \
  --kernel-build artifacts/exec-environment-kernel-NEW-build.json --tag execenvNEW
python3 scripts/stage-exec-environment-runtime.py \
  --kernel-stage artifacts/shared-remap-runtime-execenvNEW-stage.json \
  --libsystem-build runtime/libsystem-kqueue-source-PREVIOUS/build.json --tag NEW
python3 scripts/test-exec-environment.py \
  --stage artifacts/exec-environment-runtime-NEW-stage.json
python3 scripts/probe-original-coreclr-managed-environment.py \
  --runtime-profile scripts/loader-environment-runtime-profile.py \
  --stage artifacts/exec-environment-runtime-NEW-stage.json
```

NEW/PREVIOUS 替换为实际构建器输出；已有路径不可重用。最后一个探针当前仍在后续 RW 映射处失败。所有 Darling 执行通过 session.lock 串行运行，移除图形环境变量，不显示图形界面。

原版 Xcode GameAssembly 子目标命令：

```bash
python3 scripts/probe-xcode-service-runtime.py build \
  --native-codesign-stage artifacts/native-codesign-ci-v3-stage.json \
  --identity-store runtime/local-identity-xcode-empty-v1/store.plist \
  --mldr-stage artifacts/mldr-dynamic-rlimit-v3-stage.json \
  --shared-remap-stage artifacts/shared-remap-runtime-v2-stage.json \
  --libsystem-kqueue-build runtime/libsystem-kqueue-source-PREVIOUS/build.json \
  --loader-environment-stage artifacts/exec-environment-runtime-NEW-stage.json \
  --core-volume-diagnostic --cfprefsd-daemon --filecoordination \
  --xcode-arguments-file config/unity-device-gameassembly-v5-build-arguments.json \
  --timeout-seconds 600
```

静态库子目标仍显式关闭签名；最终 App 签名不由这一命令证明。原始脚本可能用清理命令掩盖 IL2CPP 非零状态，所以必须另查预期 archive、目标平台、对象和符号。

完整 Unity/UE + CocoaPods App、actool/ibtool、开发者证书/provisioning、设备信任、archive/export 和完整冷安装仍未完成。公开包只含源码、配置和证据摘要，不含 Apple/Unity 二进制、SDK、资源、证书或私钥。

## 原版 plutil 安装

环境修复后的原版 Unity 构建已越过 uname，随后在 Xcode 安装信息读取处因 `/usr/bin/plutil` 不存在而失败。直接执行现有参考输入中的苹果原版 plutil 可以读出 Xcode 版本 26.6。新增安装器只复制固定 SHA256 的原始工具到新的隔离根，不更改其字节，不把工具二进制放入公开包。

```bash
python3 scripts/stage-original-host-tools.py \
  --parent-stage artifacts/exec-environment-runtime-NEW-stage.json --tag NEW
python3 scripts/probe-original-host-tools.py \
  --stage artifacts/original-host-tools-NEW-stage.json
```

已验证候选中的绝对 `/usr/bin/plutil` 路径：提取 Xcode 版本，XML 转 binary plist，再用独立 Python plistlib 核对 UTF-8、空字符串、64 位整数、布尔值、data、数组和嵌套字典。继续构建时，将上述 Xcode 命令的 `--loader-environment-stage` 指向这个新 stage，并用 `config/unity-device-gameassembly-v6-build-arguments.json` 的新输出目录。原版工程、脚本和 xcodebuild 参数结构保留。

## 最新实际构建与下一步

加上原版 plutil 后，原版 IL2CPP 已越过前述两个问题，在原版 iOSBuildLogic 的宿主平台检查中返回 `iOS builds are not supported on this platform`。预期的 libGameAssembly.a 依然不存在；Xcode 的 BUILD SUCCEEDED 再次由原始清理脚本掩盖内部失败，未被接受。

对原版程序集只读检查确认：Bee.HostPlatform 以 `Directory.Exists("/proc")` 判断 Linux，XcodeInstallation 的支持属性直接读取 HostPlatform.IsOSX。现有 Darling server 将 Linux procfs 挂载在客体根 `/proc`；所选运行根也带有该目录。下一步需要把 macOS 客体文件系统布局和 Linux 后端的内部 procfs 访问正确分开，并验证原版平台判断及构建，不改 Unity 程序集或原工程。

`fixtures/hello/InspectManagedMethods.cs` 使用 Mono.Cecil 读取指定类型/方法的 IL 和元数据，不加载执行被检查的程序集。Mono 只运行这个自建检查器；原版 Unity 编译工具依然由 Darling 执行。本附件只保存检查器源码和结果摘要，原版程序集及完整 IL 转储留在本机证据目录。
