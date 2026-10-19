# 原版 CoreGraphics 的无界面图像处理实验

这是 alpha.5 的实验记录。后续 Swift 元数据修复、资源依赖进展与新失败见 [后续依赖检查点](../native-resource-dependencies/README.md)；其中没有宣称 actool/ibtool 或 CoreVideo 已可用。

已在 Linux x86_64/Darling 中实际调用重建的原版 Intel CoreGraphics，创建真实 CF RGB 色彩空间、绘制 2×2 红色位图、生成 CGImage，并核对读回的每个像素字节。原版 ImageIO 另行解码一个有效 PNG，91 个像素的 RGB 值全部与 Linux 侧生成的输入一致。测试移除 DISPLAY、WAYLAND_DISPLAY 和 XAUTHORITY。

这条实验使用原版图像算法，恢复共享缓存重定位、合并引用及 Swift/Objective-C 元数据；不是新增一个替代渲染器。CoreGraphics 保留 5,476 个导出，完整 Swift API 兼容性未验证。新 SIMD double3x3 常量按 SDK 的 96 字节大小、16 字节对齐构建，全部字节与原版缓存核对。

两个 rootless token 接口采用首次调用时加载原版后端的入口，避免将 C++ 初始化提前到 libSystem 初始化之前。155 次结果位检查与直接原版调用一致。新增的 sandbox_extension_release_file 入口也转发原版函数。这些是 ABI/调用路径修复，未证明 Linux 实现了 macOS SIP 或所有 Sandbox 策略。

## 已知失败

- 原版 sRGB、线性 sRGB、Display P3 对象及真实 ICC 数据可创建；**CGColorConversionInfoCreate 仍返回 NULL**。已确认实际加载原版 ColorSync，并补入框架原始 Resources；尚未确定创建失败原因。PNG 测试通过不代表跨色彩空间转换已完成。
- CoreText、字体解析器、字体注册表等原版镜像已重建；最新 actool/ibtool 实验仍缺 ATS 的 `_ATSFontFamilyFindFromQuickDrawName`。两者尚未启动成功，更没有完成资源编译。
- 这些代码没有加入已验证的原版签名构建基线；Unity/UE 导出工程、证书签名、archive/export 和完整冷重建仍未完成。

本目录包含 14 份显式源码附件和带哈希的证据摘要，不含 Apple 镜像、SDK、字体资源或其他运行输入。它不由固定 67 镜像 overlay 自动应用。请先审阅 `payload/`，在独立开发工作区合并；有冲突的现有文件应手动合并，不能直接覆盖。

## 复现 CPU 图像实验

需要现有候选工作区、固定 Intel OS 缓存/提取镜像、Xcode SDK、LLVM 19，以及前文说明的基础资源和源码重建工具。仅有 XIP 尚不足以从零组装这一候选。下列命令在开发工作区根目录运行，每个 stage tag 必须是新名称。

先从 `config/coregraphics-image-pins.json` 重建以下目标：

```bash
for target in coregraphics-resource-native fontparser-resource-native hvf-resource-native parsinginternal-resource-native; do
  python3 scripts/rebuild-c-cache-image.py --target-manifest config/coregraphics-image-pins.json \
    --target "$target" --analyze-code --experimental-swift --repair-swift-relative --collect-missing-imports
done
for target in protocolbuffer-resource-native colorsync-resource-native; do
  python3 scripts/rebuild-c-cache-image.py --target-manifest config/coregraphics-image-pins.json \
    --target "$target" --analyze-code --collect-missing-imports
done
python3 scripts/stage-simd-double-matrix.py --tag dev-v1
python3 scripts/stage-native-system-resource-exports.py --tag dev-v1 \
  --base-stage artifacts/simd-double-matrix-dev-v1-stage.json
python3 scripts/stage-coregraphics-native.py --tag dev-cpu-v1 \
  --dependency fontparser-resource-native --dependency hvf-resource-native \
  --dependency parsinginternal-resource-native --dependency protocolbuffer-resource-native \
  --dependency colorsync-resource-native \
  --simd-stage artifacts/native-system-resource-exports-dev-v1-stage.json --with-resources
python3 scripts/test-original-coregraphics-native.py --graphics-stage artifacts/coregraphics-native-dev-cpu-v1-stage.json
python3 scripts/test-rootless-token-native.py --graphics-stage artifacts/coregraphics-native-dev-cpu-v1-stage.json
python3 scripts/test-original-coregraphics-images.py --graphics-stage artifacts/coregraphics-native-dev-cpu-v1-stage.json
```

前两项功能测试已通过；最后一项分别记录 PNG 成功、颜色转换失败，**整体非零退出是当前已知结果**。PNG 输入由已有 `scripts/make-imageio-fixtures.py` 生成；已有输入和证据不要覆盖，应核对 `artifacts/imageio-input-fixtures.json` 的 SHA256。

继续字体链开发时，CoreText 使用相同 Swift 实验参数；FontRegistry、FontServices 使用 `--analyze-code --collect-missing-imports`。XTFontStaticRegistryData 仅含数据，使用 `--collect-missing-imports`，没有函数入口可供反汇编。配置已经记录核对过的原版合并引用；`resolve-coregraphics-cache-imports.py` 可用于后续诊断，只接受原依赖中的唯一精确导出及同一 StaticArrayStorage 类的两个名字，不猜测无关函数别名。

所有 stage 均写入新私有目录，不安装到系统或替换成功签名基线。实际运行共享 `runtime/session.lock`，应串行执行。
