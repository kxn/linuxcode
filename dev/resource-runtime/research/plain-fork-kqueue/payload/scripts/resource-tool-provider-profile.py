#!/usr/bin/env python3
"""Expose the exact resource-tool provider scope to source-library linkers."""
from pathlib import Path
import runpy

root = Path(__file__).resolve().parent.parent
module = runpy.run_path(str(root / 'scripts/direct-resource-tool-runtime-profile.py'))


def profile(stage, configuration):
    selected = module['profile'](stage=stage, configuration=configuration)
    command = list(selected['command'])
    for key, value in selected['direct_resource_environment']['tool_environment'].items():
        if key not in ['DYLD_LIBRARY_PATH', 'DYLD_FRAMEWORK_PATH']: continue
        index = next(i for i, argument in enumerate(command) if argument.startswith(key + '='))
        command[index] = key + '=' + value
    return {**selected, 'command': command}


def environment(profile):
    return module['environment'](profile)
