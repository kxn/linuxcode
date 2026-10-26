# Swift 数据导入与原版服务启动检查点

Linux x86_64 / Darling，保留原版 xcodebuild、工程与资源编译工具。此次改动按同一类缺口批量处理，未提升默认安装环境。尚未生成完整 Unity App，Storyboard 编译仍未通过。

原版 AppKit 的默认菜单初始化读取了丢失的 Swift value witness table，得到空地址并产生0x40字段指针。按用户提供的原始缓存证明三个唯一导出、17处原始加载指令后，补齐数据绑定；原始可执行指令不变，真实 NSMenu 初始化已通过，无图形会话。

同一检查器继续扫描当前选择的77个 Swift 框架，找到另外27个框架中的44个遗漏表、292处加载。批量重建、独立绑定检查和原版 Apple 加载器的正例/损坏对照全部通过。加上 AppKit 共47个表、309处加载。格式和绑定通过只证明这些边界，不能代替实际资源编译或最终 App 语义验证。

每个新导入要求唯一具名 SwiftCore 导出、原始88字节值见证表布局、八个原始函数指针所在代码区、直接提供者依赖、原始池槽及每条 RIP 加载指令的精确字节。准备器、重建器、独立检查器各自核对证明。错误别名、错误位置、坏指令和布局损坏等对照必须失败。

Darling objc4 现会在协议扩展方法类型表排序前复制只读表，避免修改原版 DATA_CONST。完整43个源文件重建，拥有的只读表测试和原版 NSXPCInterface 测试通过。Darling libxpc 新增读取当前执行文件签名内 XML entitlement 元数据的实现，保留布尔真假、数组与嵌套字典并返回独立对象。原版 codesign 签署的 thin/FAT32 样本及无签名对照通过；精确文件读取器另有十项 ASan/UBSan 正例与损坏对照。FAT64 在当前 Darling 中不能执行；host 文件读取测试只把已签署 thin 的原始字节包进FAT64容器，不能宣称原版 codesign 已正确签署FAT64，也不代表内核 entitlement 执行或外部进程查询已实现。

默认配置的真实 ibtool 调用已继续到 CoreSimulatorService 和 simdiskimaged。ibtoold 客户端向服务发送 kickstart 请求；先前把客户端栈误判成服务向自身递归请求的描述不成立。原版 Swift XPC 帮助框架绑定的激活函数已核对，确实来自 Darling libxpc；拥有的激活调用能进入实现。MainActor、主队列和64个实际 Swift 全局任务另有启动回归，均通过。不能仅凭原版服务等待就认定 GCD 或 Swift 执行器错误。

磁盘映像枚举还发现一个真实端口缺口：原版 IOKit 的 IOMasterPort 调用 host_get_io_main，旧 Darling 路径在没有 I/O master 时返回成功和空端口。新候选把有效 host 请求接到已存在的 org.darlinghq.iokitd bootstrap 服务，保留有效内核端口并传播错误，不合成端口或挂载成功。注册表增加 Darling 管理映像的控制器入口；尚无 attach 后端，因此初始媒体为空，打开 attach 用户客户端应明确返回 unsupported。真实端到端探针已验证同一端口、控制器稳定身份、空媒体数组和明确的 unsupported 错误。原版 IOKit 的新 Mach64 内核对象发送标记不能直接投递到用户态服务；当前候选编译六个实际 Darling IOKit C 客户端源文件，将标准注册表调用交给真实 iokitd，并保留原版其他导出。早期整库重导出的候选产生了三个 HID 类重名，因此已弃用；最终六文件候选没有这些重名。原版额外接口内部的所有路径仍未验证。

源码分别保存至既有 kxn/darling-libxpc、kxn/darling-objc4、kxn/darling-xnu 和 kxn/darling-iokitd 分支。提交身份统一 Comman Kang <kangxn@gmail.com>。此整合检查点属于 kxn/linuxcode，与 Darling 源库独立。

payload 是UTF-8开发源码和配置；reference 是报告、日志与摘要，不含 Apple/Unity 二进制、SDK、XIP、core、证书或私钥。仅靠此增量还不能冷重建完整候选；需先前检查点和用户自行提供的原始 Apple 输入。原生 Darling 会话和原版 Apple 链接必须串行。
