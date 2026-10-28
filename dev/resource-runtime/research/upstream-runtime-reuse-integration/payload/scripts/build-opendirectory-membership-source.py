#!/usr/bin/env python3
"""Build all local OpenDirectory membership daemon units without installing.

The original Libinfo client and its process/cache state remain unchanged.
Only own source and hashes are suitable for publication, not copied runtime SDKs.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-root", required=True)
    p.add_argument("--baseline", required=True)
    args = p.parse_args()
    source_root = (ROOT / args.source_root).resolve(strict=True)
    baseline = (ROOT / args.baseline).resolve(strict=True)
    assert source_root.is_relative_to(ROOT) and baseline.is_relative_to(ROOT / "runtime")
    sdk = ROOT / "runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk"
    darling = ROOT / "vendor/darling"
    folder = Path(tempfile.mkdtemp(prefix="opendirectory-membership-build-", dir=ROOT / "runtime"))
    includes = [source_root / "opendirectoryd/include", source_root / "opendirectoryd/src",
                darling / "src/external/Libinfo/membership.subproj", darling / "src/opendirectory_internal/include",
                darling / "src/external/libxpc/include", darling / "src/include"]
    names = ["main.c", "identifier-translation.c", "local-membership-check.c"]
    records, objects, dependencies = [], [], []
    for index, name in enumerate(names):
        source = source_root / "opendirectoryd/src" / name
        assert source.is_file(), source
        obj, dep, log = folder / (str(index) + ".o"), folder / (str(index) + ".d"), folder / (str(index) + ".log")
        command = ["clang-19", "-target", "x86_64-apple-macos11", "-isysroot", str(sdk),
                   *["-I" + str(x) for x in includes], "-DDARLING", "-fblocks", "-O1", "-g",
                   "-Wno-deprecated-declarations", "-MMD", "-MF", str(dep), "-c", str(source), "-o", str(obj)]
        with log.open("w") as stream:
            result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT)
        record = dict(source=str(source.relative_to(ROOT)), source_sha256=sha(source), command=command,
                      status=result.returncode, log=str(log.relative_to(ROOT)),
                      object=str(obj.relative_to(ROOT)), object_sha256=sha(obj) if obj.exists() else None)
        records.append(record)
        (folder / "compile.json").write_text(json.dumps(records, indent=2) + "\n")
        assert result.returncode == 0, log
        objects.append(obj)
        dependencies.extend(Path(x) for x in shlex.split(dep.read_text().replace("\\\n", " ").split(":", 1)[1]) if Path(x).is_file())
    output = folder / "opendirectoryd"
    link = ["ld64.lld-19", "-arch", "x86_64", "-platform_version", "macos", "11", "11",
            "-syslibroot", str(sdk), "-lSystem", "-no_fixup_chains", "-no_adhoc_codesign", *map(str, objects), "-o", str(output)]
    with (folder / "link.log").open("w") as stream:
        result = subprocess.run(link, stdout=stream, stderr=subprocess.STDOUT)
    assert result.returncode == 0, folder / "link.log"
    files = [Path(__file__), baseline, output, *objects, *dependencies,
             source_root / "opendirectoryd/CMakeLists.txt", source_root / "opendirectoryd/com.apple.opendirectoryd.plist"]
    report = dict(host_verified=True, native_verified=False, installed=False,
                  source_root=str(source_root.relative_to(ROOT)),
                  source_commit=subprocess.check_output(["git", "-C", str(source_root), "rev-parse", "HEAD"], text=True).strip(),
                  baseline=str(baseline.relative_to(ROOT)), baseline_sha256=sha(baseline),
                  binary=str(output.relative_to(ROOT)), binary_sha256=sha(output),
                  full_local_opendirectoryd_source_build=True, complete_translation_units=3,
                  original_Libinfo_client_unchanged=True, shared_library_provider_modified=False,
                  no_membership_cache=True, identifier_conversion_is_not_authorization=True,
                  units=records, link_command=link, native_execution_attempted=False,
                  files={str(x.relative_to(ROOT)): sha(x) for x in files if x.is_relative_to(ROOT)})
    destination = folder / "build.json"
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(destination)


if __name__ == "__main__":
    main()
