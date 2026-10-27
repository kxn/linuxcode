#!/usr/bin/env python3
"""Select a pinned private temporary filesystem launcher for one native session."""
from pathlib import Path
import hashlib,json
r=Path(__file__).resolve().parent.parent

def select(profile, stage):
    data=json.loads((r/stage).read_text())
    for name,digest in data['files'].items():assert hashlib.sha256((r/name).read_bytes()).hexdigest()==digest,name
    command=list(profile['command']);assert command.count(data['parent_launcher'])==1
    command[command.index(data['parent_launcher'])]=data['launcher']
    return {**profile,'command':command,'native_temporary_stage':stage}
