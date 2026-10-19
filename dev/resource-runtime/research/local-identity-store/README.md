# 原生本地签名身份查询实验

这是一项独立、可选的源码实验，尚未纳入默认启动器或固定源码 overlay。它用于解决原版 Xcode 在 `SecItemCopyMatching` 等待尚未启动的 SecurityServer 的问题。一次实际原版 Xcode 构建已越过 `GatherProvisioningInputs` 并创建构建描述，随后因缺少 `/usr/bin/derq` 失败，原生退出码 65。完整 Xcode 签名仍需实际验证。

查询结果使用原生 `SecCertificate`、`SecKey` 和 `SecIdentity` 对象。证书与 RSA 私钥先比较公钥，再构造身份；测试从返回的身份取出私钥，实际生成 SHA256/RSA 签名，并用证书公钥验证。空存储返回 ItemNotFound，锁定、损坏、权限不符、证书与密钥不匹配均返回错误。支持 identity/certificate/key 类、标签、One/All，以及已实现的 ref/data/attributes 返回形式。未配置 `LINUXCODE_IDENTITY_STORE` 时委托原有实现。

**当前存储是只读的明文 plist 原型，仅用于自生成测试身份。** 尚无加密、导入/解锁命令、EC 私钥、信任链、provisioning 或真实 Apple 开发者身份验证。它不会弹出认证窗口。未支持的查询返回错误；它不是完整 Keychain 或 SecurityServer。

在已完成本仓库固定源码 overlay，并且具备完整原版 Xcode/Darling 编译基线和 codesign-zsign v2 候选的研究工作区中，先把本目录 `scripts/`、`fixtures/`、`vendor/` 下的文件复制到工作区的同名位置。不要覆盖开发者已有修改。随后运行：

```bash
python3 scripts/stage-local-identity-store.py --tag readonly-v2
python3 scripts/test-local-identity-store.py
```

stage/tag 必须未使用。测试会在私有目录生成新的、未受信任的 RSA 测试身份；不会使用个人证书。已记录的首轮结果为 34 项原生检查通过，原生与外层退出均为 0。所有执行均移除 DISPLAY、WAYLAND_DISPLAY 和 XAUTHORITY；无需图形界面。

stage 保留现有 Security 作为私有后端，只替换选择了该 profile 的进程中的身份查询入口。默认入口、持久前缀和原版 xcodebuild 均未改写。读取的是具有明确 locked/items 状态的实际文件，不是把所有查询一律回答为空。

`kSecMatchPolicy` 和完整认证 UI 查询语义尚未实现；它不会假定未验证的证书满足签名策略。当前证明的是基本身份查询与原生密码学对象可用，而非完整签名身份选择。

附带原版 derq 的私有运行根构造脚本。使用本地 Intel 缓存和恢复映像输入时，先执行：

```bash
python3 scripts/rebuild-c-cache-image.py --target-manifest config/signing-image-pins.json \
  --target coreentitlements-signing-native --analyze-code
python3 scripts/stage-derq-runtime.py --tag original-v1 \
  --codesign-stage artifacts/codesign-zsign-adhoc-v2-stage.json
python3 scripts/test-derq-runtime.py
```

原版 derq 的两组合法 XML 转换输出已通过独立 Python DER 解码。但负向检查发现：在此候选中，损坏 XML 会得到空字典和退出码 0，因此**该测试整体仍返回非零**。这一失败保留在证据中，不能依赖 derq 单独校验输入。这里没有改写原版程序，也没有把该失败标记为通过。

附带的 Xcode 探针增加 `--identity-stage`、`--identity-store` 和 `--derq-stage`，只选择私有运行候选，原版工程和 Xcode 命令参数仍由原有配置提供。它们不自动创建个人 Keychain 或开发者身份。

补齐 derq 后的第二次全新 DerivedData 构建已实际完成 Pod 的 DER 打包、编译和静态库生成，并进入原版 Xcode 的 `CodeSign` 任务。当前失败点是命令行全局强制 `CODE_SIGNING_ALLOWED=YES`，令 Pod 静态库也被送入 codesign；适配器仅支持平面 bundle，因此明确拒绝了 `.a`。Xcode 原版产品规格中静态库默认该设置为 NO，但一般文件的真实签名兼容性仍需实现，不能把这一失败当作 App 签名成功。

`probe-original-codesign-native-identity.py` 直接按绝对路径调用未修改的 Apple codesign，绕过 zsign 命令入口，签署私有 App 副本并要求原生签名/校验状态和独立哈希验证。最新复测尚在加载阶段因缺少 AppleMobileFileIntegrity 框架失败。附带的 AMFI pin 用于继续重建研究；它不代表原版 codesign 已成功运行或签名。

先前对服务启动失败的归因需要修正：选定运行环境中的实际 sandbox 初始化返回 `Invalid argument`，并非已确认调用了 Darling 的 ENOTSUP 源码占位入口。还需区分原生 profile 编译与策略应用阶段；这里不宣称已修复该服务。
