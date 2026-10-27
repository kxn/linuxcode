# 原版 Unity/CocoaPods Release 归档与 dSYM

已通过 Linuxcode 的 PATH 入口运行原版 `xcodebuild archive -configuration Release`，原生/外层退出码均为 0，生成真实 iOS arm64 xcarchive。使用原工程的 Release 符号设置，没有注入 `DEBUG_INFORMATION_FORMAT` 覆盖值；同样保留 Xcode 工程、Podfile 和原来的测试签名参数。

实际归档中的 App、三个内嵌 Framework，以及对应的 UnityFramework 和两个 Pod 静态库，七项均通过原版严格验签和独立 CMS/CodeDirectory/页面/资源检查。签名仍使用调用者配置的临时自生成 RSA 证书，测试命令明确关闭 profile 要求；不证明 Apple 开发者 provisioning 或设备信任。

## 符号文件验证

归档生成 App 与 UnityFramework 的两个独立 dSYM。检查器解析实际 Mach-O：文件类型必须为 MH_DSYM，必须存在非空 `__DWARF,__debug_info`，DWARF 版本合法，各架构 UUID 必须与归档对应二进制完全一致。本次均为 DWARF 4：

| 产物 | debug_info 字节数 | UUID 检查 |
| --- | ---: | --- |
| uEmuera | 2,305 | 与归档 App 一致 |
| UnityFramework | 96,369,473 | 与归档 Framework 一致 |

检查的是实际符号数据和对应关系，不把 dSYMs 目录存在或一个同名文件当成生成成功。较早 Debug 归档的 dSYMs 为空记录仍保留。

## 入口与证据

继续采用包含 fork 队列修复的 `config/native-certificate-candidate-v6.json`，普通 build、Debug archive、Release archive 的项目参数由调用者决定。原生任务仍使用同一私有 Linux/Darling 环境，原版 Xcode 未修改，不使用 zsign。

- `artifacts/unity-original-release-archive-milestone-v1.json`：完整 Release/签名/符号证据。
- `runtime/linuxcode-cli/20261027T143207-ae0f32ab/plan.json`、`result.json`：实际 PATH 调用、参数转换和原生状态。
- `artifacts/unity-release-xcarchive-verified-v1.json`：归档元数据、Mach-O 平台/UUID、两个非空 dSYM 的验证。
- `artifacts/unity-release-archive-products-independent-v1.json`：七项独立签名/资源验证。
- `runtime/native-certificate-products-g3j5b2h4/result.json`：七项原版严格验证。

```bash
python3 scripts/verify-original-xcarchive.py \
  --archive runtime/unity-original-archive-lbb_k8wm/Unity-iPhone.xcarchive \
  --cli-invocation runtime/linuxcode-cli/20261027T143207-ae0f32ab \
  --independent-products artifacts/unity-release-archive-products-independent-v1.json \
  --require-dsyms --report artifacts/new-release-archive-check.json
```

检查器明确区分 CLI 原生状态记录和研究驱动报告，没有把 CLI 记录改写成未执行过的探针结果。附件不包含 Apple 二进制、App、dSYM、证书、私钥或身份库内容。

原版本地 exportArchive 已在另一份归档副本上执行，进入 IDEDistribution 后明确返回 `exportArchive No Team Found in Archive`，原生和外层均为 70；没有把失败替换为成功。当前自签测试归档没有真实 Apple Team 或描述文件，因此此里程碑不宣称 export 已通过。观察记录在 `artifacts/unity-original-export-no-team-v1.json`。真实 provisioning/设备信任、P12/EC 通用导入、UE、完整干净 Linux/XIP 重建仍待推进。
