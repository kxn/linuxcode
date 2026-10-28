# Inspect actual UE App products and CocoaPod linkage with host LLVM

`verify-unreal-pods-product.py` reads actual App products, fixture source hashes and intermediate objects. It uses the existing LLVM tools to check iPhoneOS arm64 Mach-O type, the real LocalMath archive definition, the final executable definition of `_local_add`, and the own UE module object reference. It creates a fresh report and stores each original tool command, status and output; no successful linkage is inferred from a build log.

The real 7,136-byte archive from the current original Xcode workspace passed its archive-only checks. This is explicitly a partial capability check, not a verified UE App. The App build and signing are still running separately; no App-level verifier success or codesign/CMS result is claimed here. The script launches no Darling or Apple program and modifies no project or App. Existing original codesign and independent CMS tools remain the separate signing checks.

When the App exists, run from its source workspace:

```bash
python3 scripts/verify-unreal-pods-product.py \
  --app runtime/unreal-game-project-o_lk51qs/Binaries/IOS/LinuxcodeUESmoke.app \
  --project-report runtime/unreal-game-project-o_lk51qs/unreal-pods-preparation.json \
  --require-module-reference --outdir runtime/unreal-pods-final-product-NEW
```

Actual paths are explicit; the output directory must be new. Without `--require-module-reference`, missing intermediate objects are reported as unavailable coverage. A successful archive-only result must never be treated as a successful App, signature, device launch or full build.
