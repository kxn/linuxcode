# 稳定启动时间与 Unity 资源依赖推进

本检查点修复 Darling 的 `kern.boottime` 一秒级跳变，并保存五个新的原始资源依赖候选。完整原版 Unity/CocoaPods workspace 本轮进入五 target 依赖图和实际 actool/ibtool 版本查询，原生/外层返回 65，缺 BiomePubSub。后续直接工具探测又越过该依赖，当前缺 InternationalTextSearch。**尚无完整 Unity App，AFNetworking 尚未进入 CompileC，实际资源编译仍未通过。**

## 实际时钟缺陷

旧实现每次以当前墙钟减去 Linux `sysinfo.uptime` 的整秒值，再把微秒清零。这会在秒边界让启动时间跳变，进而使苹果 libc 的 `CLOCK_MONOTONIC` 回退实现倒退。本机旧候选的 250 毫秒延时被测成约 1.25 秒或负数；另一独立检查在首个样本就发现启动 epoch 比 Linux 实际值少一秒。旧失败报告保留。

源码修正从命名空间内部 procfs 的 `stat` 读取真实 `btime`，与现有 proc_pidinfo 的启动 epoch 来源一致。它不改变 Linux 主机时钟或挂载。Linux 此接口提供整秒精度，因此微秒仍为零，不伪造额外精度。长度查询、短缓冲区错误和边界保护也经过实际 Darwin API 检查。

完整 879 单元 kernel 源码重建后，16 次串行/四线程延时通过；96 次启动时间读取均与主机 Linux `btime` 一致，单调时钟不倒退，约 2.45 秒累计时间与 Mach 原始计时器相差约 2 微秒。私有 procfs 的真实 PID、sysctl、FD、pipe、vnode 和 spawn 回归通过。原版 codesign 仍能签署已有简单 CocoaPods App 副本，XML/DER entitlements 与四种篡改拒绝通过；这不代表完整 Unity App 或开发者证书签名已完成。

源改动已经在现有 [darling-xnu 分支的 c062868](https://github.com/kxn/darling-xnu/commit/c06286876985e7dddc8b240ff6bf28b62cff4c4c) 保存，作者与提交者均为 Comman Kang。没有另建账户或分支。

## 资源与完整构建证据

新增候选包括 BiomeStreams、BiomeFoundation、BiomePubSub、ProactiveSupport 和 Intents。BiomeStreams 的五个、Intents 的六个未知引用均核对为实际共享 ObjC 类引用单元，用既有双层指针恢复逻辑处理；ProactiveSupport 的 120 项缺口全部按依赖库中地址完全一致的唯一导出补齐。没有按相邻地址猜符号，也没有为资源工具生成固定成功输出。

本轮完整 workspace 使用新 DerivedData，保持原有 Unity-iPhone scheme、五个 CocoaPods/引擎 target、iPhoneOS/arm64 和 ad-hoc 参数。它实际调用原版资源工具并因缺依赖返回 65；原始 xcodebuild/actool/ibtool 未修改。新派生目录中没有 App、UnityFramework 或 AFNetworking 最终二进制，日志也没有 CompileC 任务。

上轮 600 秒初始化等待在本轮没有复现，但**没有证明两轮差异只由时钟修正造成**。独立 CoreSimulator 探测读取到真实默认超时 20 秒，服务版本查询仍返回 NULL。原始苹果参考实现的 path 查询本身就是返回 NULL，不能据此认定 Darling 必须编造路径。服务版本查询和 bundle 注册的完整行为仍待实现/验证。本检查点没有禁用原版插件或伪造服务版本。

## 在已有完整研究基线上复现

先按前序研究附件准备原始输入与运行基线，再审阅合并 payload。`reference/source-revisions.json` 指向包含时钟修正的源码 fork。以下路径展示本机已执行的配方；已有同名产物时请使用新输出目录、tag 和报告名，保留旧证据。

```bash
python3 scripts/build-libsystem-kernel-source.py \
  --source-manifest /path/to/this-attachment/reference/source-revisions.json \
  --output-dir runtime/clockdev-kernel \
  --variant-base runtime/original-host-tools-v1/darling-root \
  --report artifacts/clockdev-kernel-build.json
python3 scripts/stage-private-procfs-runtime.py \
  --parent-stage artifacts/original-host-tools-v1-stage.json \
  --server-build runtime/shared-remap-server-67vo0b3t/stage.json \
  --kernel-build artifacts/clockdev-kernel-build.json \
  --libsystem-build runtime/libsystem-kqueue-source-gx7z94z5/build.json \
  --tag clockdev
python3 scripts/probe-boottime-clock.py --stage artifacts/private-procfs-clockdev-stage.json
python3 scripts/probe-runtime-usleep.py --stage artifacts/private-procfs-clockdev-stage.json
python3 scripts/test-private-procfs.py --stage artifacts/private-procfs-clockdev-stage.json
python3 scripts/probe-original-codesign-native-identity.py \
  --runtime-profile scripts/private-procfs-runtime-profile.py \
  --runtime-stage artifacts/private-procfs-clockdev-stage.json \
  --tamper-checks --with-entitlements
```

server/system/parent 的路径必须对应本机已构建的真实基线；源码附件没有提供这些二进制。各测试在新私有目录编译夹具，并清除图形会话环境，Darling 仍由 session.lock 串行化。

在前一附件的资源基线上构建 `biomestreams-resource-v2`、`biomefoundation-resource-v1`、`biomepubsub-resource-v1`、`proactivesupport-resource-v2` 时使用 `--lazy-functions --experimental-swift --repair-swift-relative --collect-missing-imports`；`intents-resource-v2` 使用 `--lazy-functions --analyze-code --collect-missing-imports`。依次以 `extend-coregraphics-stage.py` 追加到新 stage，再用已有配置生成器生成资源工具环境。失败的 v1 候选及审计保持原样。

`direct-resource-tool-environment-v11.json` 是本轮完整构建所用资源配置，v14 是随后最新直接探测配置。`unity-ios-cocoapods-v5-build-arguments.json` 与 `unity-ios-cocoapods-v6-probe-arguments.json` 记录实际完整构建参数；复现时调整本机路径并使用新派生目录。证据汇总器依赖本机历史报告，不能当作冷恢复入口。

这批源码没有提升固定 overlay 或默认安装候选。公开包不含 Apple/Unity 二进制、SDK、缓存、XIP、证书或私钥；完整资源输出、Unity/UE App 签名、provisioning、archive/export、稳定性及干净机器恢复仍未完成。
