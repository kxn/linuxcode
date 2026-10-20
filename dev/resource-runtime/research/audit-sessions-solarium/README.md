# 无界面会话后端与原版 AppKit 数据恢复

Darling server 为每个进程保存真实会话对象，继承 fork/exec，单调分配编号，同步 task audit token；内核 getaudit_addr/setaudit_addr 通过受验证的 RPC 读写，保留逐进程审计 mask。不是固定返回成功或虚构图形登录。537 项原生检查通过，包括两个实际 fork/exec 子进程、会话唯一性、mask 隔离、部分长度、坏指针和错误终端类型。Security 原版 SessionGetInfo 从编号 0 变为有效编号 1，属性仍为无界面 0。

源码沿用已有分支，作者和提交者均为 Comman Kang <kangxn@gmail.com>：

- [darlingserver 0df62be](https://github.com/kxn/darlingserver/commit/0df62be9b9e422ef545c9d55897965713db8c75e)
- [darling-xnu dbb6b49](https://github.com/kxn/darling-xnu/commit/dbb6b490c559f07dc2dc1f12c28afd10e39a799b)

Mach audit session ports、其他会话 auditon 查询和完整 BSM 尚未实现，非 root setter 尚无原生覆盖。

## 原版资源工具

补齐匹配系统版本的 SystemAppearance.bundle，逐文件验证 SHA；安装脚本只写自有 Darling prefix，并支持验证后重复执行。附件只含资源清单，不含苹果资源。

原版 AppKit 的 NSSolariumEnabled 从共享缓存池读取 SwiftUICore 命名 macOS enum case 的 4 字节索引，该非 stub 数据指针原先缺失。新恢复器检查原始 RIP 相对指令、直接依赖、唯一只读符号、缓存指针和原始字节，将同样的数据置于只读段并恢复精确 rebase。机器码完全保留，不替换原版函数，不放宽未知导入规则。

v2 的 4 字节新段造成 LINKEDIT 文件与虚拟地址页偏移不一致。Apple 格式检查未发现，实际加载失败并回退旧 AppKit。v3 补齐段的文件页对齐；新增检查拒绝旧 v2。实际原版 NSSolariumEnabled 重复调用通过，数据页写入受保护；缺失数据、错误值和五种实际二进制损坏均有负对照。

原版 actool/ibtool 均以状态 1 结束，错误为原版 IOKit 缺少 `_host_get_io_main`。完整 Unity/CocoaPods DD67 五 target 和 UTI 预检通过，原生/外部状态 65，CompileC 为零，尚无最终产品；完整构建报告 f107726323a5 和日志见 reference。局部验证不代表完整 App 编译或签名成功；默认安装候选未提升。

## 复现输入

payload 相对完整 Linux x86_64 开发工作区；原始日志和历史源输入用 UTF-8 JSON text 封装并记录 SHA。stage 摘要不可当作实际 stage 重建输入，完整本地报告路径及 SHA 仅供定位。需要用户自行提供对应 Xcode、SDK、系统缓存与 Unity 工程，不含 Apple/Unity 二进制、SDK、XIP、证书或私钥。历史 source manifest 应合并，不能覆盖其他修订。

```bash
python3 scripts/stage-audit-session-runtime.py --help
python3 scripts/stage-system-appearance-resources.py --help
python3 scripts/probe-audit-session-lifecycle.py --help
python3 scripts/probe-appkit-solarium-enum.py --configuration config/direct-resource-tool-environment-v122.json --baseline-probe runtime/direct-resource-tools-hh_j6kkd/result.json --stage artifacts/private-procfs-auditsession4-stage.json
python3 scripts/probe-direct-resource-tools.py --configuration config/direct-resource-tool-environment-v122.json --stage artifacts/private-procfs-auditsession4-stage.json
```

原生运行必须串行。重新构建后的报告 SHA 必须重新计算，不能将旧配置 SHA 当作跨构建输入。
