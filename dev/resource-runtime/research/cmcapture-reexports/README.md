# CMCapture 依赖、显式转导出和嵌套 framework 路径

本研究新增 42 个原版 Intel 库候选，包括 CMCapture 的 12 个强依赖、CoreBrightness 的 5 个依赖以及已选资源框架另外 25 个缺库。候选源于固定 SHA 的原始缓存和提取映像；没有提供这些框架的替代算法。最终原版工具及完整 Unity workspace 结果见 evidence.json；不能把缺库减少、版本查询或文件盘点当作完整 App 编译成功。

## 精确核对显式转导出

libSessionUtility 的 11 个未解析地址对应原版 C++ 异常 RTTI 和类型名。原始 libc++ 通过导出表显式转导出 libc++abi 中的这些符号。旧审计只查直接地址导出，漏掉了这条链。

新增 exact-reexport-imports.py 仅沿原版 export-trie 的显式符号边递归，支持每一跳的重命名和 ordinal。最终地址必须完全相等，不使用最近符号或函数体相似性；多个名字仍保持歧义，由准备器拒绝任意选择。缺失的显式边不会通过搜索其他依赖补猜。循环和非法 ordinal 被拒绝。证明记录每一跳及其原始库 SHA，准备器重新读取并独立核对全部证明和辅助脚本 SHA 后才新增绑定。

```bash
python3 scripts/audit-resource-image-imports.py \
  --target libsessionutility-resource-v1 \
  --follow-explicit-reexports \
  --output artifacts/my-session-audit.json
python3 scripts/prepare-resource-image-candidate.py \
  --from-target libsessionutility-resource-v1 \
  --exact-import-audit artifacts/my-session-audit.json \
  --target my-session-reviewed --build
```

该选项须显式启用，历史审计保持原语义。实际 13 个缺失引用全部找到唯一导出，包括上述 11 个转导出数据地址。候选 libsessionutility-resource-v3 成功重建；它仍需后续加载和实际调用验证。

## 原子发布准备清单

并行的宿主库准备与构建环境核对曾触发源码历史 JSON 的半写读取。实际完整工程驱动在启动原版 xcodebuild 前退出，此次失败独立保留。准备器现先写临时文件，再用 os.replace 发布源码历史和 pin 清单。它保证单文件读者看到完整版本；没有声称多个文件构成跨文件事务，也不允许多个准备器并行写入。

真实输入的隔离测试人为把每次写入分成两半并暂停，同时持续解析已发布文件。新实现通过；把脚本换成保存的旧版后，同一检查因 JSON 截断失败。旧版负对照首次报告匹配条件过严的记录也保留。修改中间提供库 SHA、导出链、选定符号或辅助脚本 SHA 均被拒绝。

```bash
python3 scripts/test-exact-reexport-imports.py
python3 scripts/test-reexport-resource-preparation.py
python3 scripts/test-resource-image-preparation.py
```

共 18 项测试通过。测试依赖 reference 中记录的本地实际输入和相应前序候选；它们不下载 Apple 文件。

## 保留嵌套框架路径

vImage 以及四个 Accessibility 框架嵌套于其他 framework 内。仅放置平铺的 vImage.framework 等目录不能满足带外层后缀的原始安装名。extend-coregraphics-stage.py 对嵌套库保留外层 framework、Versions 与 Frameworks 后缀，仍创建最内层 framework 的正常符号链接。

新 stage 保留所有旧文件及 SHA，在新目录补充五条原版路径，不覆盖任何已映射库或历史 stage；相同候选不会重复计入依赖数量。实际文件 SHA 和符号链接逐项核对。只读盘点显示原始 70 个已选资源框架的强依赖均有文件候选；165 个新增图形/资源候选的另一轮盘点也未发现额外缺库。这不是 dyld 符号解析、初始化或 API 行为的完成证明；弱依赖及运行时 dlopen 仍可能引入其他框架。

## 恢复范围

payload 的路径相对于完整开发工作区。reference 保存审计、准备尝试、重建摘要、原始命令及测试报告。逐槽位的完整重建报告保留在本地 runtime/rebuilt-*/reconstruction.json；大型构建报告和依赖盘点也采用注明 summary_only 的公开摘要，固定完整本地报告 SHA。完整报告可按相同输入和脚本重新生成。合并前须保存旧文件和源码 SHA 历史，不能直接覆盖现有开发修改、日志或 stage。脚本测试需要的审计原路径为 artifacts/libsessionutility-original-reexport-audit-v2.json，可从 reference 恢复；重建所用原始缓存与库仍须由本地提供。

本附件需要前序完整研究基线、Darling、LLVM、Xcode/SDK 和锁定的 Intel OS 缓存。Xcode XIP 不包含后者；本附件尚不是干净机器的一键安装环境。发布内容仅为源码、文档和元数据，不含 Apple/Unity 二进制、缓存、SDK、XIP、证书或私钥。

Darling 会话保持串行，资源工具清除 DISPLAY、WAYLAND_DISPLAY、XAUTHORITY。默认安装环境未提升。完整 Unity/UE App、真实资源产物正确性、最终链接签名、开发者身份/provisioning 和 archive/export 仍须实际验证。

完整 workspace 的 v12 尝试通过 UTI 前置检查和五 target 图，停在 CreateBuildDescription / 原版 clang 查询，600 秒后被外层强制终止（exit_status=-9、原生状态为空）。它没有到达资源工具查询，也没有最终产物；这次运行不能用来证明新依赖已被完整工程加载。另一次独立工具探测因排在该会话后面，在锁等待期间耗尽执行期限，亦不作为框架失败或成功的证据。原始报告均保留。

private v11 / graphics v100 / direct-resource v49 的独立原版工具测试实际越过缺库阶段，两项工具均因 AppleIDSSOAuthentication 导入的 _AKAuthenticationDSIDKey 未被当前 AuthKit 提供而失败。原始 AuthKit 的只读检查确认它指向 __cfstring 中长度为 6、内容为 AKDSID 的常量；本检查点尚未实现该常量，也没有实现认证 API。参考报告保存了原始导出地址、对象节、字节及来源 SHA。

最终完整 workspace 使用全新 v13 DerivedData 和 private v11 / graphics v100 / direct-resource v49，UTI 前置检查及五 target 图通过。原版 xcodebuild 实际调用 actool、ibtool --version 后因同一 AuthKit 符号缺失返回原生/外层 65，没有 CompileC 或最终 uEmuera、UnityFramework、AFNetworking 二进制。该结果取代等待状态，目标仍未完成。
