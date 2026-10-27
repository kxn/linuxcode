# 原版 xcodebuild 完整 Unity/CocoaPods 证书签名

Linux x86_64/Darling 下，原版 `xcodebuild` 已完成真实 uEmuera Unity/CocoaPods iPhoneOS arm64 工程的证书签名构建，原生和外层状态均为 0。七次 `CodeSign` 均由 Xcode 调用原版 `codesign` 完成，没有使用 zsign。

这次复用此前全新 DerivedData 构建的副本，没有重新执行 `CompileC`。源码和 DerivedData 在本次私有挂载命名空间中映射至副本，保留缓存记录的绝对路径；宿主上的原 App、CodeResources、build.db 与工程文件哈希均未改变。Xcode 工程、workspace、Podfile 和锁文件与原样例一致；样例本身仍包含前面已记录的两行 AFNetworking SDK 兼容修改。

签名使用临时自生成的 RSA 证书，不是 Apple 开发者证书。测试命令将 `CODE_SIGN_IDENTITY=-` 换成该证书 SHA-1，并显式传入 `PROVISIONING_PROFILE_REQUIRED=NO PROVISIONING_PROFILE_SUPPORTED=NO`。这验证完整构建中的真实 CMS 签名链路，不证明开发者 provisioning、真机安装或原有生产 CI 的凭据配置已经可用；没有生成或伪造 Apple 描述文件。

七个最终产物是 App、三个内嵌 Framework、单独的 UnityFramework 和两个 CocoaPods 静态库。全部通过原版 `codesign --verify --strict`。独立检查验证代码页、Info.plist、CodeResources 与资源内容，OpenSSL 只使用指定测试证书验证 CMS；不把自签证书视为受信任。

静态库同时带 SHA-1/SHA-256 CodeDirectory。独立检查同时核对 CMS 已签名的 Apple hash-agility v1/v2 属性以及每个 CodeDirectory 的代码页与特殊槽；修改备用 CodeDirectory 会失败。App 代码页、Info.plist、资源封装、内嵌 Framework 的四项独立篡改测试也均被拒绝。

## 实现与继续开发

`SecIdentityCreateWithCertificate` 现在能从显式只读身份库按公钥查找真实私钥，返回原生 identity，并保留调用者传入的证书。Xcode 实际调用该路径后，原来的缺失私钥错误消失。显式原生 keychain 参数及未选择本地身份库的调用继续使用原实现；不在这里授予证书信任。37 项原生身份/策略/私钥检查通过。源码已发布至现有 [darling-security 分支提交 f50f940](https://github.com/kxn/darling-security/commit/f50f940d254addfb74f80f5fb9edc4cda60beb6c)。

本附件的 `payload/` 保留了构建驱动、证书服务作用域组合、缓存隔离、签名检查源码与候选配置；`reference/original-file-map.json` 记录每份附件的原路径与 SHA-256。没有 Apple 二进制、App、证书、私钥或身份库内容。

在已有完整实验工作区中，按原相对路径使用这些文件。`config/native-certificate-candidate-v2.json` 选择 stage84、签名客户端 v13、独立 daemon v9、完整源码 securityd 与原版 requirement parser。它依赖已有的生成产物及其校验链，不是干净机器的安装配方。

```bash
python3 scripts/probe-original-codesign-certificate.py \
  --candidate config/native-certificate-candidate-v2.json
python3 scripts/prepare-unity-certificate-ci.py \
  --candidate config/native-certificate-candidate-v2.json \
  --identity-report runtime/实际生成的证书测试目录/result.json \
  --without-provisioning-profile
```

准备命令输出新目录；其中 `command.json` 是实际构建驱动参数数组，`prepared.json` 记录目录映射、原工程保护哈希与测试参数差异。用 Python `subprocess.run(json.load(...), check=True)` 执行数组即可，不需要修改原 Xcode 工程。各原生任务继续共用 `runtime/session.lock`，宿主编译和独立检查可并行。

## 证据与剩余范围

- 完整构建：`artifacts/unity-original-certificate-CI-milestone-v1.json`。
- 原版七项严格验签：`runtime/native-certificate-products-lanotbps/result.json`。
- 独立 CMS、页面、资源和篡改检查：`artifacts/unity-certificate-products-independent-v1.json`。
- 更早的全新缓存完整编译仍见 `loader-layout-and-fsevents` 附件；本次证书构建是增量运行。

真实开发者证书与 provisioning、archive/export、UE、完整干净 Linux/XIP 重建，以及默认安装入口自动组合新候选仍未完成。基础安装器和默认候选没有因这个研究里程碑自动升级。
