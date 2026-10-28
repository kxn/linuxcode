# 安装与使用

## 主机前提

当前实现针对 Linux x86_64、Python 3.11 以上。已在 Debian 13 开发；基础 guest rootfs 为固定 Ubuntu 24.04。需要用户命名空间、mount/PID namespace、overlayfs，以及 x86_64 工具链需要的 CPU 指令；现代 Intel 参考缓存使用 x86_64h，运行候选还需要 Haswell 级 CPU，开发工具会进一步核验。不会安装 Darling 内核模块。

主机命令：`git bash curl unzip tar cpio coreutils util-linux sudo clang-19 ld64.lld-19`。Debian 13 可安装基础依赖：

```bash
sudo apt-get update
sudo apt-get install git curl unzip tar cpio coreutils util-linux sudo clang-19 lld-19
```

运行 `python3 linuxcode.py doctor` 检查命令、用户命名空间和磁盘空间。doctor 不启动 Darling。基础安装建议至少 35 GiB 可用空间；包含系统参考缓存和全部兼容构建的研究环境需要更多空间。根 CLI 的 doctor 只验证基础前提，不能证明所有图形/线程/ABI 功能已经可用。

## 一个入口安装基础环境

```bash
python3 linuxcode.py --workspace "$HOME/.local/share/linuxcode/workspace" \
  setup --xip /absolute/path/Xcode_26.6_Universal.xip
```

该命令依次：下载固定 workspace commit 并校验脚本清单；校验主机前提；下载并核对固定 Ubuntu rootfs 与 Darling 包；在私有 mount/PID namespace 里安装包；首次初始化 Darling 前缀；Linux 原生解压 XAR/PBZX/CPIO；确认原版 xcodebuild 含 Intel slice 且字节与测试版本一致；导入前缀并执行原版 xcode-select。

只有基础 rootfs 的软件包安装需要 sudo。它发生在项目 rootfs 中，不安装 Darling 系统包到宿主 `/usr`，不启用宿主服务。发行包本身不带 Xcode；XIP 由使用者提供。XIP 内容校验不是 Apple CMS 证书链验证，安装收据会明确记录。整份 XIP SHA256 和原版 xcodebuild SHA256 都已锁定到实际测试输入。`--sha256 EXPECTED` 可显式提供本地输入摘要；无论是否提供，都拒绝未经测试的 xcodebuild 版本。

单独验证 XIP 安装与目录布局，不运行 Darling：

```bash
python3 linuxcode.py --workspace /path/to/new/workspace fetch
python3 linuxcode.py --workspace /path/to/new/workspace \
  install-xcode --xip /path/to/Xcode_26.6_Universal.xip
```

目录为 `WORKSPACE/runtime/state/prefix/Applications/Xcode.app`，原始展开目录保留在 `runtime/xcode-extract/Xcode.app`，收据在 `artifacts/distribution-xcode-install.json`。此命令不初始化前缀，也不声称 xcode-select 已完成；之后运行 setup 时，安装器只对有安装收据的纯 Xcode 离线前缀做暂存，先让 Darling 正式建立账号数据库，再移回原版 Xcode。其他未初始化目录会拒绝覆盖。此续接路径的文件操作已通过模拟初始化测试，完整 sudo/bootstrap 续接尚未在干净主机实测。已有安装有一致收据时可重复执行；不覆盖其他版本或中断产物。

## 接入成功候选

```bash
python3 linuxcode.py --workspace /path/to/existing/experiment adopt
export PATH="$HOME/.local/share/linuxcode/launcher/bin:$PATH"
cd /path/to/existing/experiment/project
xcodebuild -workspace App.xcworkspace -scheme App -sdk iphoneos CODE_SIGNING_ALLOWED=NO build
```

adopt 不复制测试环境，也不宣称干净机器已能恢复它；它核对现有 profile 的源码、构建产物和元数据哈希链，以及成功构建报告/日志和 service jobs。新增入口核对选定候选，对命令创建独立 job、脚本和日志，沿用已验证运行配置和原版服务；实际 `cd` 后调用原版 xcodebuild。不会替换用户参数为 smoke 工程参数，不会默认关闭签名。上例使用较早的 unsigned 默认候选；完整 Unity ad-hoc 和证书候选需要显式选择。

查看实际参数转换但不启动 Darling：

```bash
python3 linuxcode.py xcodebuild --dry-run -- -workspace App.xcworkspace -scheme App build
```

主机项目必须位于 WORKSPACE 内。`-project`、`-workspace`、`-derivedDataPath`、`-archivePath` 等显式路径选项转换为 guest 路径；其他参数原样转交。包含主机绝对路径的自定义 build setting、脚本或更复杂参数文件还未实现普遍转换。CI 中 PATH 设置是现有入口切换方式，CI 的 xcodebuild 命令可保留；这不代表任意脚本已具备完整 macOS 文件系统视图。

## 证书签名入口

在已有完整候选的实验工作区中，指定经过验证的证书配置和自己的身份库：

```bash
python3 linuxcode.py --workspace /path/to/experiment adopt \
  --certificate-candidate config/native-certificate-candidate-v12.json \
  --identity-store runtime/my-signing/store.plist
export PATH="$HOME/.local/share/linuxcode/launcher/bin:$PATH"
cd /path/to/experiment/my-game
xcodebuild -workspace Unity-iPhone.xcworkspace -scheme Unity-iPhone -sdk iphoneos build
```

这里继续使用工程或原 CI 的签名设置，入口不会修改 `CODE_SIGN_IDENTITY`、provisioning 设置或工程文件。完整 Unity build 已通过；此前 v6 的 Debug/Release archive 与 Release 独立符号生成也已通过；证据来自自生成测试证书及显式关闭 profile 要求的测试命令，不能据此声称 Apple 开发者 provisioning、设备安装或 export 已通过。

v12 候选采用 stage101/config154，并复用客户端 v14、独立 daemon v15、源码 SecurityServer 与完整源码 trustd。UE 调试中的 fork、时间戳、复制回退和 stat 源码修复已整合回 Unity：七个产物的原版严格验签与独立 CMS 检查通过，随后全新 Linux Unity 导出项目又在空 DerivedData 下以单次 xcodebuild 调用完成证书构建。v12/stage101 也已通过全新 Unity 项目的 Release archive：App 与 UnityFramework 的严格/CMS 验签、非空 dSYM、UUID 匹配及 LLVM 全量 DWARF 校验通过；较早 v6 记录仍保留，export 继续单独推进。每次实际运行按本次身份库配置 headless 服务；adopt 与参数预览不会创建或启动服务，也不需要旧实验私钥。身份库内容不绑定到历史测试证书，可以替换为自己的匹配 RSA 密钥和证书。运行前须满足原生 API 支持的格式：

```python
{
    "version": 1,
    "locked": False,
    "items": [{
        "label": "CI signing identity",
        "certificate": certificate_der_bytes,
        "privateKey": rsa_pkcs1_private_key_der_bytes,
    }],
}
```

也可以直接导入自己的 RSA P12：

```bash
read -rs -p 'P12 password: ' MY_P12_PASSWORD
export MY_P12_PASSWORD
python3 linuxcode.py --workspace /path/to/experiment import-identity \
  --p12 /path/to/signing.p12 --output runtime/my-signing/store.plist \
  --password-env MY_P12_PASSWORD
unset MY_P12_PASSWORD
```

密码从指定环境变量读取；输出只包含身份指纹和证书数量。工具检查密钥与证书匹配，以 `600` 权限创建文件，拒绝覆盖已有身份库，并清理临时解密文件。较旧的 P12 加密算法可显式使用 `--legacy`；同一密钥对应多张证书时，用 `--certificate-sha256` 指定叶证书。当前支持 RSA PKCS1，不支持 EC。

这是只读且未加密的身份库，不是完整系统钥匙串；请保存在工作区的 `runtime/` 私有目录中。导入不会安装 provisioning profile，也不会授予证书信任。

P12 中额外的公共证书保存为可选的 `certificates` DER 数组。客户端 v14 / daemon v15 支持查找这些链证书；原生三层链测试和原版 codesign 的完整 CMS 证书链已通过。完整 Unity 构建使用从 P12 导入的自签测试身份通过；非 Apple 的三层链被原版 Xcode 正常拒绝，不再导致 trustd 崩溃。旧 v6 候选不读取这个可选数组。测试只使用显式测试根锚点，未修改系统信任库。

`status` 的 `certificate_signing_ready` 表示已采用经过验证的证书签名运行配置；`developer_provisioning_or_device_trust_verified` 仍为 false。每次调用记录实际参数、签名作用域、服务配置和原生退出码。没有重复执行 UTI smoke 探针或列出全部服务；仍检查服务加载失败并保留构建的真实失败状态。

开发时需要保留绝对缓存路径又不改旧产物，可在采用支持目录映射的候选后设置 `LINUXCODE_WORKSPACE_BINDINGS`，指向 `runtime/` 中的 JSON 数组，每项为工作区相对目录 `{"source": "runtime/new-copy", "target": "runtime/original"}`。映射只对本次私有命名空间生效；越界、重叠或缺失目录会在启动原生命令前失败。普通构建无需设置此变量。

## 离线与公开打包

`fetch` 需要 GitHub；`cache` 可提前缓存固定基础 tar/zip。bootstrap 的 guest apt 依赖和源码子模块仍会联网，因此当前**没有完整离线 cold setup**。已有锁定 workspace、缓存和构建候选后，adopt 不需要联网；项目依赖自身可能仍需网络。

`package` 使用固定代码 allowlist，不遍历实验工作区，不收集运行时或 Apple 二进制。不提供把个人前缀自动打成公开镜像的功能。项目根下 `.local/`、运行收据、证书与 XIP 不会纳入源包。需要本机归档时应自行将 Apple 输入和私有材料放在自己的存储中，公开发布只使用 source 包。

默认包也保留后续研究源码、显式打包 spec 和 README，可用 `python3 dev/research-sources.py list` 发现并核验；详见[研究源码审阅指南](../dev/research-sources.md)。历史 `reference/` 证据默认省略，添加 `package --include-research-history` 才包含。导出研究源码供合并审阅不会安装 stage104/106 或自动重建最新成功候选。

## 固定源码和模块开发

整合工程独立于 Darling 源码仓库。开发模块位于 `dev/`，可从根 CLI 转交参数：

```bash
python3 linuxcode.py --workspace /path/to/experiment dev doctor
python3 linuxcode.py --workspace /path/to/experiment dev sources verify
python3 linuxcode.py --workspace /path/to/experiment dev build journal
python3 linuxcode.py --workspace /path/to/experiment dev build server --plan
```

开发入口的精确依赖和命令见 [dev/README.md](../dev/README.md)。普通基础安装不自动拉取所有研究仓库；`restore-sources` 或开发源码命令才会按锁定版本恢复它们。

旧 milestone 的历史文件清单曾列入 11 个未实际发布到 Git 的 CocoaPods 生成文件。整合工程已锁定修正后的 r1 commit：清单只包含实际公开的文件，fetch 对修正清单全部严格核验。原始失败日志和输入说明保留在验证证据中，没有为缺失文件制造占位内容。

长时间引擎构建可只调整环境变量，保留原 CI 命令：

```bash
export LINUXCODE_BUILD_TIMEOUT_SECONDS=3600
xcodebuild -workspace App.xcworkspace -scheme App -sdk iphoneos build
```

默认 600 秒，可配置范围为 1–86,400 秒；超时会保留真实失败状态和调用日志，不会当作构建成功。

## 选用原版签名候选

在已有完整研究运行时中，先构造并实际验证 [原版 codesign 候选](../dev/resource-runtime/research/native-codesign/README.md)，再接入本机的成功报告：

```bash
python3 linuxcode.py --workspace /path/to/experiment adopt \
  --native-codesign-stage artifacts/native-codesign-ci-v3-stage.json \
  --identity-store runtime/local-identity-xcode-empty-v1/store.plist \
  --build-report artifacts/xcode-service-runtime-tool-dispatch-diagnostic-build-270c91d1646a.json \
  --product-report artifacts/ios-cocoapods-native-signed-product.json
export PATH="$HOME/.local/share/linuxcode/launcher/bin:$PATH"
```

报告路径以本机实际结果为准。入口核对产物、静态库签名扩展属性、同一候选和原生退出证据，再保留 CI 中的工作目录及 xcodebuild 参数。该入口已从项目目录、全新 DerivedData 实际完成 CocoaPods iOS App 编译和原版 ad-hoc 签名，且独立复核了 App 和两个静态库。主机与 Darling 内的显示相关环境变量均移除。

`status` 会显示 `signing_scope: ad-hoc` 和 `certificate_signing_ready: false`。这不是开发者证书签名、Unity/UE 兼容性或完整冷安装成功的声明。

## 选择已验证的 Unity 候选

这一步用于已有完整研究运行环境，不能替代从 XIP 安装基础环境，也不自动冷重建全部依赖：

```bash
python3 linuxcode.py --workspace /path/to/experiment adopt \
  --engine-milestone artifacts/unity-original-signed-app-v1.json
```

将命令打印的目录加入 PATH 后，保留 CI 现有 xcodebuild 参数。入口验证原始成功构建与六项签名验证记录，选择对应运行库和资源工具环境，并执行记录中的服务准备步骤。签名范围为 ad-hoc；开发者证书、描述文件和设备安装尚未验证。详情见[Unity 签名里程碑](../dev/resource-runtime/research/unity-signed-app/README.md)。


## Unity Editor 的 Linux 授权入口

Unity Editor 和授权工具均使用原生 Linux 版。已有的 Xcode/Darling 环境不需要运行 Unity Hub。

```bash
python3 linuxcode.py --workspace /path/to/experiment unity auth login
```

入口会按固定的官方 SHA256 下载 Unity CLI 1.0.0-beta.14 到工作区 `runtime/` 中。登录命令会显示官方链接；远程或无界面机器可以在自己的浏览器打开它，保持命令等待，直到登录完成。链接有时效，超时后重新运行登录命令。

确认符合并同意 Unity Personal 条款后，可以由账号本人执行：

```bash
python3 linuxcode.py --workspace /path/to/experiment unity license activate --personal --accept-eula
```

`--accept-eula` 是官方 CLI 要求的显式条款接受选项，工具不会自动添加。账号凭据由官方 CLI 管理，Linuxcode 不记录密码或令牌。当前测试机器已完成官方网页登录、Personal 激活，并由无图形界面的原生 Linux Unity 6000.3.27f1 成功导出全新 iOS Xcode 工程；随后原版 CocoaPods、空 DerivedData 中单次原版 Xcode 构建和正常退出、原版证书签名及严格验签和独立 CMS 检查均已通过。当前使用自生成 P12 测试证书，尚未验证 Apple 开发者 provisioning 或设备安装。若 SSH/自动化父进程的 session keyring 已失效，入口会只在自己的进程树中建立可用的用户凭据 keyring，不修改父进程。修复已由官方 CLI doctor 和实际登录、激活验证。

官方说明：[Unity CLI](https://docs.unity.com/en-us/unity-cli/use-unity-cli)。
