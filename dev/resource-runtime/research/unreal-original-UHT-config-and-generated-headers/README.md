# Original UHT processes the iOS manifest after restoring its configuration

The original Xcode external UE script now passes the earlier first-use temporary-directory failure. Its original BuildUBT.sh completes the managed build/publication and invokes the game UBT target. That Xcode attempt still returns 75 because internal UHT rejects delegate macros.

The parser implementation was correct. Our initial sparse engine input selection omitted `Engine/Programs/UnrealHeaderTool/Config/DefaultEngine.ini`, which supplies the delegate-parameter suffix table and other UHT settings. The file was restored byte-for-byte from the pinned official engine commit. The same original Mac UBT assembly's UnrealHeaderTool mode then processed the existing 235-module iOS manifest under Darling, wrote 11,804 generated files, and returned native/outer status zero. No UHT parser or engine implementation was changed.

The omitted Engine/Programs tree contains only 59 tracked inputs. The remaining 58 original config/helper files (119,977 bytes) were restored from the pinned Git blobs with their original executable modes, preserving existing files. The sparse checkout was not reapplied, and downloaded SDK paths were not pruned. Records contain hashes and Git object IDs; Epic source contents, generated headers and original tool logs remain private.

Run the attached original-tool arguments through the existing `probe-unreal-dotnet-runtime.py` with stage103, config154, the existing private temporary-stage selector and persistent CLI home. This is a focused UHT boundary test. The original Xcode game build continues separately on the corrected inputs; full UE C++/App compilation, signing and UE CocoaPods integration remain unverified.

The integrated attempt also recorded one CLR RW/RX mapping fatal error followed by the upstream dotnet retry and eventual managed build success. This remains a runtime reliability issue; the generic message does not prove memory exhaustion. The server fault watcher saw normal namespace teardown and produced no crash core for that attempt.
