# 原版 Contacts 依赖组与批量格式验证

本附件继续在纯 Linux x86_64 / Darling 上运行原版 actool、ibtool 和 Unity/CocoaPods 构建。原版工具、工程和命令保持不变；实际资源编译、完整 Unity/UE App 链接和签名仍未完成，默认安装候选没有提升。最新实际失败和产物检查见 evidence.json。

## 恢复原始依赖组

ScreenTimeCore 需要 Contacts 的 CNDowntimeWhitelist 类。原始导出表确认它属于原版 Contacts，未创建替代类。Contacts 首次重建因 380 个原始跳转桩 GOT 引用未核验而停止；独立原始依赖导出审计全部找到唯一身份，准备器重新核验后才生成第二份候选。

物理依赖检查还发现七个缺失的强依赖：ContactsPersistence、AppleLDAP、CoreSuggestions、ContactsFoundation、vCard、ContactsMetrics、ProactiveEventTracker。八个原版映像均以保留指令方式构造；ContactsPersistence、ContactsFoundation、vCard、ProactiveEventTracker 的额外导入也经独立审计。八份独立检查合计验证 3659 个 GOT 单元和 17609 个序列化绑定，原始可执行节字节全部一致。

这只证明候选的代码和结构，没有声称 Contacts 数据库、LDAP、建议服务或其他完整 API 行为已验证。原版工具随后越过此前类缺失，又暴露 ContactsFoundation 所需的 DataDetectorsCore 常量 DDBinderCityKey；追加第九个原版映像并验证后，工具继续推进到 Vision 的 VNCreateImageFingerprintsRequest 类缺失。

## 批量准备时保留明确选项

prepare-resource-dependency-batch.py 新增 preparation_options 配置，仅接受已支持的独立布尔选项。旧配置默认行为保留。启用 preserve-code-with-patch-got 时，批次必须核对每个成功候选的零指令修改、原可执行节证明和无 backend-call override；不能因批量执行而丢掉指令保留选项。

批次顺序执行各准备器，保留所有尝试和日志。现在也能识别原始跳转桩 GOT 未覆盖的诊断，先审计真实缺失引用，再由准备器重新核验。未知失败继续保留为失败；--keep-going 只收集独立失败，整个未完成批次仍退出非零。

本地构造了 graphics v119 和 contacts-closure-v1 overlay，随后追加 DataDetectorsCore 形成 v120 / contacts-datadetectors-v1。它们是独立目录，没有覆盖旧映像或更改普通构建进程的框架路径；只有原有 actool/ibtool 子进程作用域选用新配置。

## 在同一原生会话验证多份映像

probe-original-dyld-validation-batch.py 使用与 XIP 提取件逐字节相同的苹果 dyld_info，在一个串行 Darling 会话执行八个格式正例及十六个损坏副本对照。每个 target 生成独立的验证报告，记录真实原生命令状态，供既有独立检查器使用。重复或未知结果标记会拒绝，任一正例或对照不符合预期则整个批次失败。

Contacts 的单映像验证与批量报告已独立比较：映像 SHA、原始 UUID、工具 SHA、状态和三个用例结果完全一致。批量不会把格式验证说成框架运行或资源编译成功。另有九个实际候选的内存篡改拒绝检查；DataDetectorsCore 独立通过了原版 dyld_info 正例和两个损坏对照。

## 在完整开发基线上使用

需要前序附件的完整源码和运行根、本地锁定的 Intel cache/提取件、Xcode/SDK 和 LLVM。payload 相对于完整工作区，需审阅合并并保留精确源码 SHA 历史。配置中的参考 target/tag 和报告路径不可直接覆盖使用；为自己的批次修改为新名字，并核对 already prepared 的 target。

```bash
python3 scripts/prepare-resource-dependency-batch.py \
  --configuration config/my-original-dependencies.json \
  --report artifacts/my-original-dependencies.json --keep-going
python3 scripts/probe-original-dyld-validation-batch.py \
  --preparation-report artifacts/my-original-dependencies.json \
  --stage artifacts/private-procfs-v11-stage.json
```

批量格式探测返回新的 result.json，reports 数组逐个列出独立报告。对每个候选运行 inspect-preserved-patch-got.py，使用对应的 --original-validator-report；仍需独立的原始指令/绑定和损坏控制，不能仅凭构建器成功选择候选。

原生命令清除 DISPLAY、WAYLAND_DISPLAY、XAUTHORITY，所有 Darling 会话串行。reference 日志以 JSON text 保存原始 UTF-8 字节，original-file-map.json 提供 SHA；summary_only 文件只是完整本地报告摘要。公开包不含 Apple/Unity 二进制、SDK、cache、XIP、证书或私钥。完整冷安装和完整 App 仍须后续验证。
