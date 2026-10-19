# 原版 codesign 与完整 ad-hoc 构建里程碑

已在 Linux x86_64/Darling 中实际完成两次全新 DerivedData 的 CocoaPods/UIKit iPhoneOS/arm64 App 编译和签名：一次由原版 Xcode 服务探针运行，一次通过整合工程安装到 PATH 的普通 `xcodebuild` 入口运行。两个 Pod 静态库和最终 App 均执行了原版 `codesign`；原生命令与外层退出均为 0。整条候选流程不调用 zsign。

原版工具独立签署带资源、XML/DER entitlements 的 App 后，原版校验和 Linux 独立校验均通过。代码页、Info.plist、资源和新增文件四种篡改，均被两者拒绝。实际 Xcode 构建产物又单独经过原版校验和独立哈希检查。静态库使用真实扩展属性保存签名，包含已核对的 SHA1/SHA256 CodeDirectory；复制这些库时需要保留扩展属性，才能继续校验库自身的签名。

**范围仍是 ad-hoc 及简单 CocoaPods 夹具。** 开发者证书、provisioning、设备安装、Unity/UE 导出工程、actool/ibtool 和完整冷安装均未完成。运行仍需要现有 CoreServices 诊断策略。当前本地身份库为只读明文研究原型；完整 Keychain、信任服务、远程签名和新 launch/library constraints 没有实现，未支持的请求返回错误。

## 实际修改

- 原版 `xcodebuild`、`codesign` 和 `codesign_allocate` 的文件字节保留。签名器使用已有 Security 后端的真实本地签名实现，新增接口兼容层；没有把签名或验证改成固定成功。
- 补齐重建的原版 AMFI、libTLE 和 CoreEntitlements 依赖；补充从固定原始映像核对的常量。系统密钥入口委托已有 token-key 后端，不生成替代硬件密钥。
- 从完整 879 个源码单元构建 `libsystem_kernel`，将 Darwin 扩展属性映射为实际 Linux `user.*` inode 属性，修正路径/描述符列举及错误返回；39 项检查和原有活动 Quarantine 策略回归通过。
- `F_NOCACHE` 使用 Linux 的实际 NOREUSE/NORMAL 缓存提示，保留普通未对齐读写；不承诺完全相同的 macOS 缓存策略。
- Xcode 显式指定分配器时会触发尚未工作的信任服务。候选只把**已固定哈希的同一原版 Xcode 分配器**安装到隔离的默认系统位置，并规范化这个已知路径的环境变量；自定义分配器覆盖仍保留。原版签名器使用自己的默认分配器流程，不修改信任判断结果。

所有测试移除 DISPLAY、WAYLAND_DISPLAY 和 XAUTHORITY，无图形界面。挂载、启动器和运行根均为私有候选，默认入口和持久 codesign 文件不变；持久前缀中也没有新增 codesign_allocate 文件。

## 继续开发

这是显式源码附件，不由固定 67 项 overlay 自动应用。需要完整的已有研究基线、用户自己的 Xcode/Intel 系统参考输入，以及前一份 [身份存储附件](../local-identity-store/README.md)。单独解压本源包并不等于已经具备完整运行环境。

先将 `payload/` 的文件复制到研究工作区的同名路径，检查并保留已有开发修改。参考 JSON 只是版本、哈希和接口值，不含 Apple 二进制、证书或私钥：

```bash
mkdir -p /path/to/workspace/runtime/security-upstream-reference
cp reference/security-system-key-source.json /path/to/workspace/runtime/security-upstream-reference/source.json
cp reference/security-signer-constants.json /path/to/workspace/artifacts/original-codesign-security-constant-reference.json
```

以下名字是本次实测用的固定候选名，输出已存在时会拒绝覆盖；重复实验请换新工作区或一致调整对应路径。

```bash
python3 scripts/rebuild-c-cache-image.py --target-manifest config/signing-image-pins.json --target coreentitlements-signing-native --analyze-code
python3 scripts/rebuild-c-cache-image.py --target-manifest config/signing-image-pins.json --target amfi-signing-native --analyze-code
python3 scripts/rebuild-c-cache-image.py --target-manifest config/signing-image-pins.json --target libtle-dylib-resource-native --analyze-code
python3 scripts/stage-local-identity-store.py --tag readonly-v2
python3 scripts/build-security-system-key.py --tag v2
python3 scripts/build-security-code-signer-compat.py --tag v2
python3 scripts/stage-original-codesign-closure.py --tag native-local-signer-v1 \
  --target amfi-signing-native --target libtle-dylib-resource-native \
  --security-stage artifacts/security-code-signer-compat-v2-stage.json
python3 scripts/stage-derq-runtime.py --tag original-v1 \
  --dispatch-stage artifacts/resource-tool-dispatch-guest-identity-apple80211-v1-stage.json
python3 scripts/build-libsystem-kernel-source.py --output-dir runtime/xattr-kernel-source-v3 \
  --variant-base runtime/derq-original-v1/normal/darling-root \
  --report artifacts/xattr-kernel-source-v3-build.json
python3 scripts/stage-xattr-runtime.py --tag v3 --derq-stage artifacts/derq-original-v1-stage.json \
  --kernel-build artifacts/xattr-kernel-source-v3-build.json
python3 scripts/stage-native-codesign-runtime.py --tag ci-v3 \
  --dispatch-stage artifacts/resource-tool-dispatch-guest-identity-apple80211-v1-stage.json \
  --xattr-stage artifacts/xattr-runtime-v3-stage.json \
  --identity-stage artifacts/local-identity-store-readonly-v2-stage.json \
  --closure-stage artifacts/original-codesign-closure-native-local-signer-v1-stage.json
```

kernel 构建也可传 `--source-manifest /path/to/linuxcode/dev/locks/source-manifest.json`，接受清单中以同一固定 base 保存的精确 fork HEAD。源输入仍逐文件记录 SHA256；其他未知 HEAD 被拒绝。完整的干净 fork 冷重建还未验证。

ad-hoc 测试需要实际初始化的空身份库。使用已有测试生成的 `runtime/local-identity-xcode-empty-v1/store.plist`，或创建 version=1、locked=false、items=[] 的 plist，文件权限 0600。缺失、损坏和锁定的文件会失败，不会被当作空身份库。

```bash
python3 scripts/test-darwin-xattr-namespace.py --xattr-stage artifacts/xattr-runtime-v3-stage.json
python3 scripts/test-xattr-quarantine-regression.py --xattr-stage artifacts/xattr-runtime-v3-stage.json
python3 scripts/probe-original-codesign-native-identity.py \
  --native-codesign-stage artifacts/native-codesign-ci-v3-stage.json --tamper-checks --with-entitlements
python3 scripts/probe-xcode-service-runtime.py build \
  --native-codesign-stage artifacts/native-codesign-ci-v3-stage.json \
  --identity-store runtime/local-identity-xcode-empty-v1/store.plist \
  --core-volume-diagnostic --cfprefsd-daemon --filecoordination \
  --prebuild-command-file config/ios-cocoapods-prebuild-arguments.json \
  --xcode-arguments-file config/ios-cocoapods-native-codesign-v2-build-arguments.json --timeout-seconds 600
```

原版 derq 的合法转换已验证；损坏 XML 被转为空字典并退出 0 的负向失败仍保留，不能依赖它单独校验输入。`verify-apple-legacy-entitlements.py` 专门校验旧 SET 格式：Apple [布尔值回归](https://github.com/apple-oss-distributions/Security/blob/db15acbe6a7f257a859ad9a3bb86097bfe0679d9/OSX/utilities/Regressions/su-12-cfboolean-der.c) 明确使用 01 表示 true；严格的现代 CoreEntitlements v1 校验器没有因此放宽。

## 使用普通 CI 命令

先对本机实际成功构建执行 `verify-ios-cocoapods-product.py` 和 `verify-native-codesign-product.py`，保存原生/独立验证报告，再执行一次 `adopt`：

```bash
python3 linuxcode.py --workspace /path/to/workspace adopt \
  --native-codesign-stage artifacts/native-codesign-ci-v3-stage.json \
  --identity-store runtime/local-identity-xcode-empty-v1/store.plist \
  --build-report artifacts/xcode-service-runtime-tool-dispatch-diagnostic-build-270c91d1646a.json \
  --product-report artifacts/ios-cocoapods-native-signed-product.json
export PATH="$HOME/.local/share/linuxcode/launcher/bin:$PATH"
cd /path/to/workspace/project
xcodebuild <原来的参数>
```

报告名字必须替换为本机实际产生的成功报告。adopt 核对同一签名候选、实际产物字节、静态库签名扩展属性、日志和服务配置；不能借用其他候选的通过报告。该 PATH 入口已从项目子目录、全新 DerivedData 实际完成编译和签名；正常的工作目录和路径参数保留。这里不需要构建或安装 zsign。
