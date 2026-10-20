# 原版 Vision 依赖组与 TextRecognition 元数据边界

本附件继续在纯 Linux x86_64 / Darling 上运行原版 Xcode 工具。恢复 Vision 及八个原始依赖，保留所有原版可执行节字节。原版 actool/ibtool 已越过 VNCreateImageFingerprintsRequest 缺失，随后在 UnifiedAssetFramework 所需的 MobileAsset 类 MAThirdPartyCompatibility 处失败。实际资源编译和完整 Unity/UE App 构建、签名仍未完成；最新完整工程结果与产物检查见 evidence.json。默认安装候选没有提升。

## 原始代码与导入身份

新增候选为 Vision、CoreSceneUnderstanding、VisionCore、libfaceCore.dylib、Futhark、InertiaCam、TextRecognition、DataDetection、CVNLP。每份候选均独立检查可执行节、原始地址、GOT 和序列化绑定；原版 dyld_info 在一个串行 Darling 会话检查九个正例和十八个损坏对照。格式检查不代表完整框架 API 已验证。

Vision、CoreSceneUnderstanding 和 libfaceCore 使用的数学函数地址存在四个同地址导出。分别核对原始跳转桩、GOT 补丁记录以及 libSystem 的真实重导出路径后，仅 _scalbn 身份通过验证。未按同地址别名随意选择函数。初次准备、失败审计及重试均保留。

## TextRecognition 的错误来自元数据解析

恢复器最初把 __swift5_typeref 中一段二进制泛型环境当成类型名称，读出两个无效外部指针，因此拒绝生成映像。诊断追踪确认无效值来自 Swift symbolic-reference 扫描，没有将其伪装成缺失符号或补零后放行。

原版 __const 中的 KeyPath 模式 0x7ff918c3f078 直接引用泛型环境 0x7ff918c43f20；其 root type 独立指向 0x7ff918c43f2c，确定环境长度为十二字节。环境包含两层泛型参数与声明的两个 marker 约束，实际未发出 requirement 记录。这个布局与先前已验证的 Swift marker 约束省略行为一致。

新 fixture 进一步使用原版 Apple Swift 编译器生成相同布局：flags=8194、累计参数数目 1/2、两个 0x80 参数描述符，以及零条 requirement。IR 检查通过，生成程序实际执行了两次不同具体类型的 KeyPath 访问。此测试证明该编译器布局及 fixture 行为，没有声称已执行 TextRecognition 的完整 API。

准备器新增 --swift-keypath-environment-bounds，读取明确的 JSON 边界列表；仍由既有校验器核对原版字节 SHA、环境引用、独立 root/leaf 标签和重复记录。恢复时保留原始 header，仅按已验证边界解析。六个实际记录损坏/引用/边界对照必须拒绝；原版机器码保持一致。

## 在开发工作区使用

payload 相对于完整开发工作区。需要此前附件、锁定的 Intel cache/提取件、Xcode/SDK 和 LLVM；公开材料不包含这些二进制。配置使用本地实验 target/tag，运行前应选择自己的新名字，并保留配置与源码 SHA 历史。coregraphics-image-pins.json 是本次快照，合并时必须保留其他开发者的 target。

```bash
python3 scripts/prepare-resource-image-candidate.py \
  --from-target vision-closure-textrecognition-resource-v1 \
  --exact-import-audit artifacts/vision-closure-textrecognition-original-import-audit-v1.json \
  --verified-subset-import-audit --target my-textrecognition-v1 \
  --swift-keypath-pattern 0x7ff918c3f078 \
  --swift-keypath-environment-bounds config/textrecognition-keypath-environment-bounds-v1.json \
  --preserve-code-with-patch-got --patch-got-renamed-reexports \
  --preserve-original-uuid --read-only-data-const --align-linkedit-streams \
  --omit-lazy-helper-section --omit-leading-padding-sections --build
```

随后独立检查指令与绑定，并运行原版 dyld 格式验证、原版资源工具和实际工程。不要将重建成功或 --version 成功视为资源编译成功。

graphics v121 和 vision-closure-v1 overlay 是独立目录，仅选入原有 actool/ibtool 子进程作用域。所有原生会话串行，测试清除 DISPLAY、WAYLAND_DISPLAY、XAUTHORITY，不启动图形界面。reference 中日志与 LLVM IR 以 JSON text 保存，original-file-map.json 提供原始 SHA；summary_only 文件只是完整本地报告摘要。公开包不含 Apple/Unity 二进制、SDK、cache、XIP、证书或私钥。
