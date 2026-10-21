# CoreSimulator 磁盘服务与 Swift 版本检查

Linux x86_64 / Darling 的增量开发检查点；沿用原版 Xcode 工程、xcodebuild 和资源工具，无 Mac、无图形会话。默认安装候选没有升级，实际 Storyboard 与最终 Unity App 仍未生成。须与先前的 unity-coresimulator-services 检查点结合使用。

原版 simdiskimaged 已进入 Swift ImageManager 初始化。启动原版 configd 与 diskarbitrationd 后，独立原生客户端确认 DASessionCreate 真正成功，先前的 diskArbitrationUnavailable 错误不再出现。DiskImages2、APFS、DiskImages、MediaKit 和完整 DiskManagement 的候选均保留原始可执行字节和 VM 偏移，经过独立绑定检查及原版 Apple dyld 正例/损坏对照。格式验证不证明磁盘映像挂载、媒体枚举、cryptex、模拟器运行时安装或所有 API 已实现。

MediaKit 的一个 _wait4 导入没有 dyld patch 记录。新检查器用原始 stub 指令、GOT 地址、间接符号表、未定义符号及库序号共同证明导入身份；仅凭目标地址不够，因为 _wait4 与 ___wait4_nocancel 地址相同。正例和六项损坏/错误别名对照通过。准备、重建与独立检查各自重新核对这份证明，不能用手工填入的名字代替验证。

提交给 launchd 的任务现在收到已有的三个 Darling 加载器作用域环境变量；拥有的原生进程回归确认环境送达且调用者的 plist 没有被修改。源码来源与提交见 reference。

Swift 调用的 _availability_version_check 原先始终返回 false。现在按原版 Intel 的 uint32_t count 与八字节 platform/version ABI，使用实际 kern.osproductversion 比较第一个匹配平台；没有匹配平台表示不加约束。14项原生用例覆盖空列表、当前/旧/未来版本、多平台、重复条目及空指针防御，真实任务生命周期回归也通过。SystemVersion.plist 报告26.6.2，内核既有配置报告26.2；差异仍存在，测试对独立 sysctl 查询核对，不把版本号当作 API 能力证明。

当前启动阻塞仍在原版 CoreSimulator 与 simdiskimaged 的同步请求。--diagnostic-disable-volume-manager 使用原版 NSArgumentDomain 参数 -EnableVolumeManager NO，只有诊断用途：它绕过原版服务初始化时过早向自身发送请求的路径，不能作为默认修复。最新原版 Storyboard 的真实结果与日志均保留；仅创建 listener 不等于完成激活或成功应答。没有安装完整 iOS Simulator Runtime。

```bash
python3 scripts/build-libxpc-source.py --output-dir runtime/新目录 --report artifacts/新构建.json --variant-base runtime/既有候选/darling-root
python3 scripts/stage-user-bundle-runtime.py --parent-stage artifacts/既有stage.json --build artifacts/新构建.json --tag 新标签
python3 scripts/probe-availability-version.py --configuration config/direct-resource-tool-environment-v136.json --stage artifacts/新stage.json
python3 scripts/probe-original-storyboard.py --configuration config/direct-resource-tool-environment-v136.json --stage artifacts/新stage.json --with-disk-services --diagnostic-disable-volume-manager
```

原生会话和 Apple 原生链接须串行。冷重建仍依赖此前检查点和用户自行提供的 Apple 输入。reference/original-file-map.json 记录源路径和 SHA-256；UTF-8 包装需还原精确字节，历史输入需合并保存。stage 仅存摘要，不能直接用作运行配置。公开附件不含 Apple/Unity 二进制、SDK、XIP、core、证书或私钥。
