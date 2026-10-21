# CoreSimulator 服务注册与 launchd 任务

这是 Linux x86_64 / Darling 的源码研究检查点。保留原版 xcodebuild、工程和资源工具；不需要 Mac，也不启动图形界面。默认安装器候选没有升级，完整 Unity App 与实际 Storyboard 编译仍未完成。

原版 CoreSimulatorService 已从 bootstrap 连接失败推进到执行 main。libxpc 现在能发现已加载框架中的 User XPC 服务，读取 versioned framework 的 Resources/Info.plist，向真实 launchd 注册按需任务并查询其版本/路径。声明的服务环境和 Darling 的显式可执行文件作用域会送到实际服务进程。元数据查询读取已注册任务对应的磁盘 bundle；不保证原地升级后识别仍映射旧版本的进程。Application/System XPC bundle 域、原地升级和删除仍未实现。

真实服务注册暴露了二进制 plist UTF-16 长度单位错误：原实现把 code units 当成 bytes，转换失败后解引用空对象。修复乘2和边界检查、转换失败处理与空字符串。11项独立生成的原生测试覆盖中文、emoji、奇偶长度、长字符串、组合字符、空值及畸形长度。这不代表整个 plist 解析器已全面验证。

原版 AppServerSupport 候选保留原始可执行字节和 VM 偏移，独立核对108个 GOT 单元与194个绑定；原版 Apple dyld_info 的正例和损坏对照通过。实际服务已经加载该框架并进入 main。RTLD_NOW 的另一个探针会遇到未使用的 Rosetta 导入；实际 ibtool 使用延迟绑定，该导入不是已证明的阻塞点。

按原版 Intel ABI 实现 job/domain 的同步和异步包装：job 子系统10、domain 子系统3，异步第三参数是 Mach 回复端口。未知操作仍返回真实 ENOTSUP；测试核对来自 PID1/euid0 的回复。xpc_strerror 的普通 errno 已调用 strerror，扩展 XPC 错误目前仅返回通用文字。

原版服务发出的实际请求是1005按标签查找，以及1011提交 simdiskimaged。launchd 现将 plist 转换为现有任务导入器的输入，分配稳定 UUID，并支持1006真实启动和1003移除。当前只支持隔离 launchd 的 System 域、euid0调用者与无监控任务；其他域和监控明确返回不支持。沿用真实 Mach 审计身份和现有 sandbox job-creation 查询。拥有的原生回归通过真实进程启动、PID与XPC回复匹配、环境送达、重复提交拒绝、畸形嵌套值拒绝、移除后失效句柄拒绝。没有把不支持的操作伪造成成功。

DD76完整重跑仍以65退出，但58个 CompileC、3个 CodeSign 和3个 CopyPNGFile已执行。Data 的2880个文件与输入逐字节一致；实际3个 PNG 像素一致；已有框架和两个 Pod 的独立签名检查通过。以上不能代表最终 App 已完成。

源码保存在 kxn/darling 与 kxn/darling-libxpc 原有 linuxcode/xcode-x86_64 分支；具体提交和原生报告见 reference。作者和提交者均为 Comman Kang <kangxn@gmail.com>。payload 的源码覆盖在锁定源树上；reference/original-file-map.json 记录原路径与摘要，UTF-8包装需恢复原字节，历史输入应合并保存。stage摘要是研究记录，不是可直接运行的完整stage。冷重建仍依赖先前检查点与用户自己提供的 Apple 输入。

```bash
python3 scripts/build-libxpc-source.py --output-dir runtime/新XPC目录 --report artifacts/新XPC报告.json --variant-base runtime/既有候选/darling-root
python3 scripts/stage-user-bundle-runtime.py --parent-stage artifacts/既有stage.json --build artifacts/新XPC报告.json --tag 新标签
python3 scripts/build-launchd-job-source.py --parent-stage artifacts/新XPCstage.json --output-dir runtime/新launchd目录 --report artifacts/新launchd报告.json
python3 scripts/stage-launchd-job-runtime.py --parent-stage artifacts/新XPCstage.json --build artifacts/新launchd报告.json --tag 另一个新标签
python3 scripts/probe-launch-job-lifecycle.py --configuration config/direct-resource-tool-environment-v133.json --stage artifacts/新launchdstage.json
python3 scripts/probe-original-storyboard.py --configuration config/direct-resource-tool-environment-v133.json --stage artifacts/新launchdstage.json
```

Darling原生运行与Apple原生链接须串行。可选 --trace-launch-jobs 明确开启请求字典诊断，仅用于自己的测试输入；默认不输出任务字典。公开附件不含 Apple/Unity 二进制、SDK、XIP、core、证书或私钥。
