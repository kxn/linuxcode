# Unity 编译、原版签名与 Unicode 路径检查点

原版 xcodebuild 已在 Linux x86_64 / Darling 内完成 UnityFramework 的 C/C++ 编译、链接，并调用原版 codesign 对 framework 和两个 Pod 静态库作 ad-hoc 签名。独立检查通过 framework 的 26153 个代码页、3 个特殊槽和9项资源，以及两个静态库的签名目录。DerivedData 中58个编译对象和最终 framework 都是 arm64 Mach-O。此时完整工作区仍返回65，最终 uEmuera.app 尚未生成；两条 CompileStoryboard 只说明任务被调度，不证明实际输出成功。开发者证书、provisioning、设备信任均未验证。

这一轮使用独立的 iOS26 SDK 兼容样本副本：只删除 AFNetworking 两个 .m 文件中多余的私有 netinet6/in6.h 导入。原版 Apple Clang 的独立对照已证明新 SDK 会拒绝该导入，公共 netinet/in.h 已提供相应类型。原始样本保持不变，23个 Xcode/CocoaPods 配置文件和5979个其他文件逐字节相同；没有关闭诊断。这个两行样本修正不计为 Darling 兼容修复。

工作区失败在 Data 目录复制：原版 Swift/Foundation 文件信息查询把 NFC 文件名转换为 NFD，Linux 按字节查找得到 ENOENT。原版 Foundation 的直接目录复制能通过，但原版 Swift 的递归属性查询在第186项重现错误。新的 Darling vchroot 在精确字节查找失败后匹配 Unicode 规范等价拼写，更新实际路径长度，再按正常规则跟随符号链接；碰到多个规范等价候选时返回错误。未改资源文件、SwiftBuild 或 Xcode 工具。

修复采用固定版本 utf8proc 2.12.0 的规范分解，保留来源、原始 SHA256 和许可。实现使用有界栈缓冲区，不引入堆分配或新的公共导出；879个源文件中只有 vchroot 的对象变化。完整原有导出保留。原版 Swift 随后通过全部3041项文件/目录遍历；源码宿主测试58项、Darling 原生路径/保护页/32次链接上限/64KB线程栈检查176项通过。完整 Unicode 大小写折叠、HFS 排除规则和所有文件系统竞争条件不在已验证范围。

源码已提交到 kxn/darling-xnu 的原分支 linuxcode/xcode-x86_64，提交 af1cf29efa1a348b0d764b3c64673877104eff16。作者与提交者均为 Comman Kang <kangxn@gmail.com>。本附件仍在整合仓库 main；不升级默认安装基线。

## 开发复现

payload 以完整研究工作区为相对根路径。reference/original-file-map.json 记录原始 SHA256、包装位置和是否只有摘要；UTF-8 包装的 text 可还原原始字节。上游 Unicode 数据的原始尾随空白特意保留，因此存为 JSON 包装。历史源输入应合并保留。报告中的运行时路径和 SHA 依赖之前的候选，摘要不能直接启动；重新生成时使用新输出目录和 tag，不能覆盖已映射文件。

```bash
python3 scripts/test-vchroot-unicode-host.py
python3 scripts/probe-original-swift-directory-info.py --configuration config/direct-resource-tool-environment-v130.json --stage artifacts/private-procfs-auditsession7-stage.json --source runtime/unity-ios-cocoapods-ios26-v1/ios/Data
python3 scripts/probe-vchroot-source-regressions.py --configuration config/direct-resource-tool-environment-v130.json --stage artifacts/private-procfs-auditsession7-stage.json
```

Darling 原生运行和原生链接必须串行。DD72 / v80 在 Unity 原生编译中途遇到 darlingserver SIGABRT，xcodebuild 随后退出132；没有验证到完整 App。core 栈指向 S2C mmap 回复的无期限信号量等待，却得到 THREAD_TIMED_OUT；后续信号已经到达，回复对象也存在。独立公有 semaphore API 测试确认旧的已提前完成等待仍留下计时器，令下一次无期限等待错误返回49。按照 XNU sched_prim.c 的 thread_unblock 补回取消等待计时器及 active 引用记账后，四轮正例和真正超时对照共39项通过。修复提交 bbc98906758b0be71271fe9f171824c1148e25b9 位于现有 kxn/darlingserver 分支，提交身份同上。此修改没有将超时一律当成功，也未降低编译并发度。新的完整工程参数为 v81 / DD73，结果须另行核验。公开包仅含我们编写的代码、第三方开源 Unicode 实现、参数和验证记录，不含 Apple/Unity 二进制、SDK、XIP、证书或私钥。完整候选的冷重建仍未完成。
