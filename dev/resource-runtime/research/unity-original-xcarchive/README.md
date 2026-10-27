# 原版 Unity/CocoaPods Debug xcarchive

纯 Linux x86_64/Darling 下，原版 `xcodebuild archive` 已完成真实 Unity/CocoaPods 工程的 Debug 归档，原生/外层状态均为 0，生成真实的 `Unity-iPhone.xcarchive`。本次包含完整 IL2CPP/Bee、59 项原生 CompileC、链接、strip 和七次原版 CodeSign。

已核对归档 Info.plist 的 ArchiveVersion、scheme、App 路径、标识和架构；实际主程序为 iOS arm64。归档内 App、三个内嵌 Framework，以及对应的 UnityFramework 和两个 Pod 静态库，共七项通过原版严格验签及独立 CMS、页面与资源验证。证书仍是调用者提供的临时自签测试身份，测试命令显式关闭 profile 要求，没有 Apple 开发者 provisioning 或设备信任证明。

Debug 归档包含 dSYMs 目录，但其中没有文件；本里程碑明确不声称独立符号生成已经通过。后续 Release 归档会额外检查 App、UnityFramework 的 dSYM 类型、非空 DWARF 内容，以及 UUID 与对应归档二进制一致。这里只记录已经完成的 Debug 结果，archive/export 的其他配置仍需各自实测。

## 运行配置

该归档使用 stage85，修复前在 fork 子进程复制文件描述符时停住；原因与 old142/new0 定向验证见 `spawn-kqueue-fork-reset` 附件。仅重编译一个 kernel 源文件，原版 Xcode 未修改。

`config/native-certificate-candidate-v6.json` 把 stage85 与这次成功归档、七项严格验签、独立产物检查和成功日志关联，可供整合 CLI 采用：

```bash
python3 linuxcode.py --workspace /path/to/experiment adopt \
  --certificate-candidate config/native-certificate-candidate-v6.json \
  --identity-store runtime/my-signing/store.plist
```

之后保留原有 CI 的 xcodebuild 参数。入口现在分别核对 `BUILD SUCCEEDED` 和 `ARCHIVE SUCCEEDED`，不能用普通 build 的绿色日志代替归档成功。新增两项回归验证这个区别；前面已通过且未受影响的入口测试没有重复执行。

## 证据和源码

- `artifacts/unity-original-archive-milestone-v1.json`：结合真实归档、原版严格验证和独立结果的回执。
- `artifacts/unity-original-xcarchive-verified-v1.json`：归档 metadata、Mach-O 架构/UUID 和零项独立 dSYM 的明确记录。
- `artifacts/unity-original-archive-products-independent-v1.json`：七项 CMS/CodeDirectory/资源验证。
- `runtime/native-certificate-products-lhwa6_0h/result.json`：七项原版严格验证。
- `scripts/verify-original-xcarchive.py`：独立归档检查器；`--require-dsyms` 强制 App 和 UnityFramework 的实际 DWARF/UUID 检查。

归档重跑和 Release 准备均使用私有缓存副本，原来验证过的 App、Xcode 工程和日志保留。源码附件不包含 Apple 二进制、App、证书、私钥或身份库内容。原生执行继续串行，宿主独立检查与源码发布可并行。
