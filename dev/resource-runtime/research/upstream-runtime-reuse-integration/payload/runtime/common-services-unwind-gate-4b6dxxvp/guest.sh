#!/bin/bash
set -euo pipefail
ulimit -c 0
run_phase() {
    phase=$1; shift
    printf "SVC_UNWIND_GATE_PHASE_BEGIN %s\n" "$phase"
    if "$@"; then
        printf "SVC_UNWIND_GATE_PHASE_STATUS %s 0\n" "$phase"
    else
        status=$?
        printf "SVC_UNWIND_GATE_PHASE_STATUS %s %s\n" "$phase" "$status"
        exit "$status"
    fi
}
run_phase diskarbitration /Volumes/SystemRoot/workspace/runtime/common-services-unwind-gate-4b6dxxvp/diskarbitration-probe
run_phase systemconfiguration /Volumes/SystemRoot/workspace/runtime/diskarbitration-service/store-client
run_phase static-unwind-walk /Volumes/SystemRoot/workspace/runtime/unwind-sections-smoke-v13/probe
run_phase native-exceptions /Volumes/SystemRoot/workspace/runtime/common-services-unwind-gate-4b6dxxvp/exceptions-probe
run_phase managed-implicit-null /Volumes/SystemRoot/workspace/runtime/unity-coreclr-mutex-68waptyq/probe /Volumes/SystemRoot/workspace/runtime/unity-macos-editor-6000.3.27f1-v1/Unity/Unity.app/Contents/Helpers/UnityLicensingClient.app/Contents/MacOS /Volumes/SystemRoot/workspace/runtime/managed-implicit-null-v15/ManagedImplicitNullSmoke.exe
printf "SVC_UNWIND_GATE_COMPLETE phases=5\n"
