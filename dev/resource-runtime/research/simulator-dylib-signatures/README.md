# 模拟器动态库签名、Swift 兼容库与宿主接口

纯 Linux x86_64 / Darling、原版 Xcode 和原工程/CI 参数保持。原版 dyld_sim 已实际运行 IBAgent-iOS，并开始装载原版模拟器 QuartzCore、Foundation 和 libdispatch；仍没有生成最终 Unity App 或 Storyboard 产物，默认安装候选未提升。

F_ADDFILESIGS_FOR_DYLD_SIM（83）验证 Apple 平台身份；F_ADDFILESIGS_RETURN（97）登记普通代码覆盖范围。最初把二者接到同一平台策略后，真实 Swift Open Source Developer ID 库被拒绝。现有两个独立 RPC：83继续要求 Apple Software Signing 的根/中间证书/叶标记；97验证 Apple 根下具备代码签名用途的 CMS，或实际哈希正确的 ad-hoc CodeDirectory。Developer ID 和 ad-hoc 不能获得平台身份。普通 OpenSSL 不理解 Developer ID Application 的 critical 标记，新的处理只识别精确 OID 1.2.840.113635.100.6.1.13、唯一扩展和 DER NULL 值；其他未知 critical 扩展仍拒绝。没有通用忽略 critical 扩展。链、CMS、每页代码和存在的特殊槽位照常校验。

主机 ASan/UBSan 对照验证平台签名、Developer ID、ad-hoc 的正确区分及损坏代码拒绝；既有14项平台策略对照也保留通过。Darling 主加载器静态入口通过97的真实描述符、范围、覆盖输出和错误内存等七组测试。原版资源流程随后进入 IBAgent-iOS，先前缺失的97接口已越过。源码发布在 kxn/darlingserver 与 kxn/darling-xnu 的原有 linuxcode/xcode-x86_64 分支，提交身份始终为 Comman Kang <kangxn@gmail.com>。

下一处是既有兼容 libswiftC6 的代码页和旧 CMS 不一致。最初尝试保留旧签名元数据，原版 codesign 在验证旧时间戳时等待尚未完成的信任服务，记录保留。新的构建只处理私有副本：去除无效旧签名的负载命令，明确提供标识符/选项，再用原版 codesign 产生新的本地 ad-hoc 签名。原文件没有修改；86个 Mach-O 代码/数据节、两个 CPU slice 均保持内容一致。原版严格校验与独立逐页/特殊槽位校验通过。新独立校验器还检查嵌入的 Info.plist 和 FAT 各 slice。修正校验器后复用了已经签好的输出，没有再次执行签名。

原版 codesign 产生的 ad-hoc 文件含精确8字节空 CMS 外壳，后端支持该正常形式，仍拒绝带非空 CMS 的 ad-hoc 身份；修改后的代码页也被拒绝。签名报告和补充报告明确区分代码节保持、重新产生的本地身份与元数据：此次调用虽然传入原有 entitlements，工具没有为该动态库输出 entitlement 槽位，未声称保留库的全部签名元数据。这个副本通过当前会话中的只读绑定提供，不改变原始 prefix 文件，也不具有 Apple 平台身份。

资源加载又暴露 voucher_mach_msg_clear 缺失。新内核实现保留其他消息字段，COPY_SEND仅清除消息中的 voucher 字段，MOVE_SEND还释放一个真实发送权；未知 disposition保持。真实 Mach 权利计数和重复清理测试通过。这个改动不声称实现完整线程 voucher 上下文采纳。

随后缺失的 pthread_yield_np 来自上游已经存在、此前未应用的 alias 列表。开发源码补齐链接配置；私有运行库一次加入 pthread_yield_np、cthread_yield、_pthread_is_threaded 三个别名，均直接指向既有目标。导出表之外的原有 slice 字节不变，i386 slice也原样保留。原生测试检查精确目标地址，并运行真正的调度和线程创建/回收。这里未完整重建 pthread 源码库，链接配置的完整构建仍未验证；这次运行的是经过字节和目标校验的导出表更新。

最新原版 Storyboard 记录是 runtime/original-storyboard-4609y9tu/result.json，已继续到原版 iOS libdispatch 的 mach_eventlink_associate 缺失。对应 XNU 实现已在 Darling 服务源码中，用户态 MIG/系统调用接线尚待补齐。附件保留各次失败和实际通过的局部测试，不能据此认定完整 App 构建成功。

开发者需要此前研究基线及自行取得的 Xcode/SDK/运行时。payload 提供源码、私有签名/挂载、真实权限测试、别名生成和逐页校验脚本。附件仅包含 UTF-8 源码、日志、报告与摘要；没有 Swift/Apple/Unity 二进制、SDK、XIP、CMS 输入、core 或私钥。未重新运行未受影响的旧 Swift、完整 Unity CompileC 和 App 签名测试。
