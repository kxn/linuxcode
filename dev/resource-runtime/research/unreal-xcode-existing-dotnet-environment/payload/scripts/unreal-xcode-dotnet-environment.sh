#!/bin/bash
# Source this file in the Xcode session so its original child tools inherit
# the same official dotnet environment as the successful standalone UBT run.
export DOTNET_CLI_HOME=/Volumes/SystemRoot/workspace/runtime/unreal-dotnet-cli-home-v1
export NUGET_PACKAGES=/Volumes/SystemRoot/workspace/runtime/unreal-nuget-packages-v1
export DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE=1
export DOTNET_CLI_TELEMETRY_OPTOUT=1
export DOTNET_GENERATE_ASPNET_CERTIFICATE=false
export DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1
export DOTNET_MULTILEVEL_LOOKUP=0
/bin/bash /Volumes/SystemRoot/workspace/runtime/unity-recvfrom-dd76-v1/prebuild.sh
