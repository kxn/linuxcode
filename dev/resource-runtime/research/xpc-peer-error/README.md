# XPC 后端错误单例与原版资源依赖推进

这批更新把 BiomeFoundation 所需的 `_xpc_error_peer_code_signing_requirement` 放进 Darling libxpc 后端，并让已有富错误适配库重导出同一个对象。它新增一个真实不可变错误对象，没有新增 peer 签名验证能力。全局对象描述与锁定原版参考一致：`Peer Forbidden`。开发者证书、provisioning 和完整 Unity/UE App 仍未通过。

## 实际缺陷与修复

先前原版 actool/ibtool 已越过 AppSupport 等缺失库，随后在 BiomeFoundation 缺少这个符号。直接在资源 libSystem 增加指向 ObjC 适配库的重导出虽然推进了符号绑定，独立程序却暴露 `libc++0` 初始化循环。失败报告保留在 reference 中；最终方案不使用该候选。

最终 libxpc 使用既有错误/字典/字符串类型和全局引用计数规则存储单例，不增加 dylib 依赖边。完整 40 个源文件重建后，上一实际候选的 641 个导出全部保留，唯一新增导出是此错误对象，112 个 launch 重导出也保留。适配库通过已有 libxpc 依赖的 ordinal 重导出对象，保留全部原有导出和指令字节，不再定义第二份单例。

独立测试在旧运行时确认 libSystem 确实找不到该符号；最终候选的资源和普通运行入口分别通过 `RTLD_FIRST` 查询 libSystem 和适配库，指针完全相同。两种入口分别执行的 160 项真实富错误对象创建、复制、引用、描述与 retry 检查以及错误单例类型/内容/引用/副本隔离通过。既有错误对象 copy 返回 dictionary 的基础限制仍保留，没有宣称修复。

源码保存在现有 [darling-libxpc 分支的 05f54c8](https://github.com/kxn/darling-libxpc/commit/05f54c8bc6fcbc38c54e829e65a107f238d3e031)。作者、提交者均为 Comman Kang，没有新建账户或分支。

## 在已有研究工作区构造候选

需要前序研究基线及锁定的 Apple 输入。合并 payload 前，保存将被替换的旧源码和清单到 `runtime/source-input-history` 并维护其 manifest；旧运行时证据仍按原始 SHA 解析。XPC activation profile 的源码检查现支持这些精确历史快照，实际二进制 SHA 检查保留。不要覆盖旧候选、日志或报告。

```bash
python3 scripts/build-libxpc-source.py \
  --output-dir runtime/my-peer-xpc \
  --report artifacts/my-peer-xpc.json \
  --variant-base runtime/private-procfs-v7/darling-root
python3 scripts/build-xpc-rich-error.py \
  --source-peer-error artifacts/my-peer-xpc.json \
  --output-dir runtime/my-peer-adapter \
  --report artifacts/my-peer-adapter.json
python3 scripts/stage-peer-error-runtime.py \
  --parent-stage artifacts/private-procfs-v7-stage.json \
  --libxpc-build artifacts/my-peer-xpc.json \
  --graphics-parent artifacts/coregraphics-native-v76-stage.json \
  --adapter-report artifacts/my-peer-adapter.json \
  --runtime-tag mynewpeer --graphics-tag mynewpeer
```

应成对选择新 libxpc 与适配库；混用旧适配库会产生两份不同的错误单例。stage 工具核对源文件/库 SHA 与适配库的同后端关系，构造全新目录，同时替换私有根和 source_runtime 的 libxpc，并把配套适配库放进普通入口的 libraries 和私有根 usr/lib，保留旧进程/内核/系统库。新 graphics stage 将对应适配库放在原有搜索路径前部。资源 libSystem 使用之前完整源码候选，不增加指向 ObjC 适配库的新边。

按新 stage 的实际路径/SHA 生成配置后，运行：

```bash
python3 scripts/probe-resource-system-peer-error.py \
  --stage artifacts/private-procfs-mynewpeer-stage.json \
  --configuration config/my-peer-resource-environment.json \
  --control-stage artifacts/private-procfs-v7-stage.json \
  --control-configuration config/direct-resource-tool-environment-v29.json \
  --provider runtime/coregraphics-native-mynewpeer/libraries/libDarlingXPCRichError.dylib \
  --check-normal-runtime
```

必须给出实际被选中的适配库路径；测试保留严格的实现归属核对。Darling 仍通过 session.lock 串行运行；探测清除图形会话环境，没有显示服务要求。

## 资源链与范围

本轮另外重建并追加九个原版候选：AppSupport、CorePhoneNumbers、IntentsFoundation、FrontBoardServices、GeoServicesCore、BoardServices、BackBoardServices、GeoServices、AssertionServices。GeoServices 恢复了 2,967 个类和 10,956 个导出；CorePhoneNumbers 的 58 项、GeoServices 的 390 项导入均按原始依赖中地址完全一致的导出处理。静态路径清单严格区分弱加载项与强依赖，不把路径推测当作 dyld 实测。

原版工具已越过这一批依赖与 XPC/AssertionServices 符号，现在缺 CloudKit 的 `CKAccountChangedNotification`。这些库的完整算法语义仍未逐项验证。完整 Unity/CocoaPods 使用全新 DerivedData 的实测结果见 evidence；它仍保留原始五 target、scheme、iPhoneOS/arm64 和 ad-hoc 参数。实际资源输出、完整 App 链接签名、UE、开发者证书、archive/export 和干净机器恢复仍需继续。

本附件不升级固定 overlay 或默认安装候选，不包含 Apple/Unity 二进制、SDK、缓存、XIP、证书或私钥。已有 Intel 系统缓存参考输入仍是额外前提，Xcode XIP 不包含它们。

最新完整 workspace 使用 private-procfs v9 / graphics v78 / direct-resource 配置 v33，实际原生和外层均返回 65，已到五 target 依赖图和真实 actool/ibtool 查询。最终失败为 CoreDuet 在 CloudKit 中找不到 `CKAccountChangedNotification`。新 DerivedData 没有 CompileC 任务，也没有 App、UnityFramework 或 AFNetworking 最终二进制。该结论不把工具加载推进当作资源编译成功。

普通入口的独立检查曾发现旧适配库仍在搜索路径中，单例指针与 libSystem 不同；该失败保留为 `reference/normal-entry-pairing-rejection.json`。最终 stage 同时选择普通入口和资源入口的配套库，两个入口都通过完整对象身份与行为检查。v8/v32 及较早构建参数保留作历史记录；最终候选使用 private-procfs v9 / graphics v78 / direct-resource v33，以及 v8 build / v9 probe 参数。
