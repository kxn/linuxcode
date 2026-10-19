# CoreGraphics 名称接口的研究材料

这些文件保留本地 70 映像资源实验中的源码；不由资源/签名 overlay 自动应用，不改变安装器基线。完整 actool/ibtool 仍未启动成功，当前观察到的下一个接口缺口是 TextureIO 所需的 `_CGColorSpaceGetType`。

`CGColorSpaceNames.m` 根据实际 Onyx2D 状态实现 Get/Copy 名称和 CoreFoundation 所有权，并修正已有命名工厂对 Display P3 名称的遗漏；设备 Gray/RGB/CMYK 使用参考映像中的系统名称。未知命名空间仍由原工厂返回 NULL。渲染后端保持原有实现，ICC 转换和颜色管理没有因此补齐。

实际 Darwin 调用已核对 sRGB、Display P3、三种设备空间、NULL、未知名称，以及 Copy 返回值在释放空间后的可用性；`dladdr` 确认执行的是新源码 facade。测试在编译基线的库路径下运行，避免其他尚缺接口的资源映像在测试开始前失败。

继续实验需要完整兼容候选以及 Onyx2D 开源头文件。先保留已有开发文件，再把同名字的源码/夹具分别放到工作区 `vendor/darling/src/external/cocotron/CoreGraphics/`、`fixtures/hello/`，把两个 Python 文件放到 `scripts/`。stage 脚本固定使用全新的 `runtime/cg-colorspace-names-v2`，会复用已验证的原 backend、CGFloat、CGContext 和 accelerator 对象，实际重新链接源码 facade，再恢复既有 ImageIO 常量。它不会安装进默认根；已有同名输出时拒绝覆盖。

70 项 pin 文件仅供审阅、合并新增的 CoreWiFi、IPConfiguration、IO80211 三项。IPConfiguration 没有 ObjC 类但具有协议定义，必须保留 `restore_objc_protocols` 标记。现有 67 项源码重建基线保持不变；合并前核对自己的配置和原始输入 SHA256。只有这些 pins 不能自动组装完整运行环境。

`cg-colorspace-names-profile.py` 支持明确的 resource stage 和 graphics stage。单独验证夹具时使用 `include_resource_environment=False`；实际资源探测必须保留资源环境，此时依然会在后续接口加载失败。此目录不提供成功资源编译、Unity/UE 或签名集成的证明。
