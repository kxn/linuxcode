#!/usr/bin/env python3
"""Inventory x86_64 Mach-O load-command dependencies in the isolated prefix.

This is a static inventory, not proof of symbol/ABI/initializer compatibility.
Uses each image's first encountered rpath context; dlopen/plugin dependencies
outside the two explicit seeds are not inferred.
"""
from collections import defaultdict, deque
from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path
import posixpath
import re
import struct

project=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--seed',action='append',help='Guest absolute path; repeat for additional seeds')
parser.add_argument('--native-stage',action='store_true',help='Include the experimental framework/library search paths')
parser.add_argument('--runtime-root',type=Path,help='Project-local private Darling directory variant, used below the prefix overlay')
parser.add_argument('--framework-stage',action='append',type=Path,default=[],help='Project-local framework stage, searched before the native/default paths')
parser.add_argument('--library-stage',action='append',type=Path,default=[],help='Project-local library stage, searched before the native/default paths')
parser.add_argument('--library-path',action='append',default=[],help='Guest DYLD_LIBRARY_PATH entry; repeat in search order')
parser.add_argument('--output',type=Path,help='Inventory JSON output path')
args=parser.parse_args()
args.framework_stage=[stage.resolve() for stage in args.framework_stage]
args.library_stage=[stage.resolve() for stage in args.library_stage]
for stage in args.framework_stage+args.library_stage:
    if not stage.resolve().is_relative_to(project/'runtime'):
        parser.error('Custom stages must be inside this project runtime directory')
runtime_root=args.runtime_root.resolve() if args.runtime_root else project/'runtime/rootfs/usr/libexec/darling'
if not runtime_root.is_dir() or not runtime_root.is_relative_to(project/'runtime'):
    parser.error('Runtime root must be an existing directory inside this project runtime directory')
roots=[project/'runtime/state/prefix',runtime_root]
app='/Applications/Xcode.app/Contents'
executable=app+'/Developer/usr/bin/xcodebuild'
seed_loader=app+'/Frameworks/libxcodebuildLoader.dylib'

def resolve_guest(path):
    path=posixpath.normpath(path)
    framework=re.search(r'([^/]+\.framework)/(?:Versions/[^/]+/)?([^/]+)$',path)
    # dyld2.cpp getFrameworkPartialPath requires the leaf to equal the
    # innermost framework name. An embedded dylib such as
    # Vision.framework/libfaceCore.dylib uses DYLD_LIBRARY_PATH instead.
    if framework and framework[2]!=framework[1].removesuffix('.framework'):
        framework=None
    candidates=[]
    if framework:
        candidates.extend(stage/framework[1]/framework[2] for stage in args.framework_stage)
    elif path.endswith('.dylib'):
        candidates.extend(stage/posixpath.basename(path) for stage in args.library_stage)
    staged=next((candidate for candidate in candidates if candidate.is_file()),None)
    if staged:return staged,path
    if args.native_stage:
        candidates=[]
        if framework:
            candidates.append(project/'runtime/native-framework-stage'/framework[1]/framework[2])
        elif path.endswith('.dylib'):
            candidates.extend(project/directory/posixpath.basename(path) for directory in
                ('runtime/native-library-stage','runtime/rebuilt-der'))
        staged=next((candidate for candidate in candidates if candidate.is_file()),None)
        if staged:return staged,path
    for _ in range(40):
        parts=path.lstrip('/').split('/')
        restarted=False
        for i in range(len(parts)):
            partial='/'.join(parts[:i+1])
            candidate=next((root/partial for root in roots
                            if (root/partial).exists() or (root/partial).is_symlink()),None)
            if candidate is None:return None
            if candidate.is_symlink():
                target=os.readlink(candidate)
                if not target.startswith('/'):target='/'+posixpath.join(posixpath.dirname(partial),target)
                path=posixpath.normpath(posixpath.join(target,*parts[i+1:]))
                restarted=True
                break
        if not restarted:return candidate,path
    raise ValueError('Guest symlink loop: '+path)

def load_commands(path):
    with path.open('rb') as stream:
        header=stream.read(32)
        offset=0
        if header[:4] in (b'\xca\xfe\xba\xbe',b'\xbe\xba\xfe\xca',b'\xca\xfe\xba\xbf'):
            endian='>' if header[:4]!=b'\xbe\xba\xfe\xca' else '<'
            count=struct.unpack_from(endian+'I',header,4)[0]
            width=32 if header[:4]==b'\xca\xfe\xba\xbf' else 20
            stream.seek(8)
            entries=stream.read(count*width)
            for i in range(count):
                if struct.unpack_from(endian+'I',entries,i*width)[0]==0x1000007:
                    offset=struct.unpack_from(endian+('Q' if width==32 else 'I'),entries,i*width+8)[0]
                    break
            else:raise ValueError('No x86_64 slice')
            stream.seek(offset)
            header=stream.read(32)
        if header[:4]!=b'\xcf\xfa\xed\xfe':raise ValueError('Not a little-endian 64-bit Mach-O image')
        if struct.unpack_from('<I',header,4)[0]!=0x1000007:raise ValueError('Not x86_64')
        count,size=struct.unpack_from('<II',header,16)
        data=stream.read(size)
    dependencies=[]
    rpaths=[]
    cursor=0
    for _ in range(count):
        command,length=struct.unpack_from('<II',data,cursor)
        if length<8 or cursor+length>len(data):raise ValueError('Invalid load command extent')
        if command in (0xc,0x80000018,0x8000001f,0x20,0x80000023,0x8000001c):
            name_offset=struct.unpack_from('<I',data,cursor+8)[0]
            name=data[cursor+name_offset:cursor+length].split(b'\0')[0].decode()
            if command==0x8000001c:rpaths.append(name)
            else:dependencies.append((name,command==0x80000018))
        cursor+=length
    return dependencies,rpaths

def expand(path,loader):
    for token,base in [('@loader_path',posixpath.dirname(loader)),
                       ('@executable_path',posixpath.dirname(executable))]:
        if path==token or path.startswith(token+'/'):path=base+path[len(token):]
    return posixpath.normpath(path)

queue=deque((seed,()) for seed in args.seed) if args.seed else deque([
    (executable,()),(seed_loader,(app,app+'/Frameworks',app+'/SharedFrameworks'))])
seen=set()
missing=defaultdict(set)
weak_missing=defaultdict(set)
invalid=[]
images=[]
image_records={}
while queue:
    image,inherited=queue.popleft()
    resolved=resolve_guest(image)
    if resolved is None:
        missing[image].add('<seed>');continue
    host,canonical=resolved
    identity=str(host)
    if identity in seen:
        if identity in image_records:
            aliases=image_records[identity]['aliases']
            for alias in (image,canonical):
                if alias not in aliases:aliases.append(alias)
        continue
    seen.add(identity)
    try:dependencies,rpaths=load_commands(host)
    except (ValueError,struct.error) as error:
        invalid.append({'image':image,'error':str(error)});continue
    search=tuple(dict.fromkeys([expand(p,image) for p in rpaths]+list(inherited)))
    record={'image':image,'host':str(host.relative_to(project)),
            'aliases':list(dict.fromkeys([image,canonical])),
            'dependencies':len(dependencies)}
    images.append(record);image_records[identity]=record
    for name,weak in dependencies:
        candidates=[expand(name,image)]
        if name.startswith('@rpath/'):
            candidates=[posixpath.join(base,name[len('@rpath/'):]) for base in search]
        if name.endswith('.dylib'):
            candidates=[posixpath.join(base,posixpath.basename(name)) for base in args.library_path]+candidates
        found=next((p for p in candidates if p.startswith('/') and resolve_guest(p) is not None),None)
        if found:queue.append((found,search))
        else:(weak_missing if weak else missing)[name].add(image)

report={'checked_at':datetime.now(timezone.utc).isoformat(),
        'scope':__doc__,'images_visited':len(images),'images':images,
        'runtime_root':str(runtime_root.relative_to(project)),
        'overlay_prefix':'runtime/state/prefix',
        'native_stage_included':args.native_stage,
        'framework_stages':[str(p) for p in args.framework_stage],
        'library_stages':[str(p) for p in args.library_stage],
        'library_search_paths':args.library_path,
        'missing_required_images':[{'name':key,'consumers':sorted(value)} for key,value in sorted(missing.items())],
        'missing_weak_images':[{'name':key,'consumers':sorted(value)} for key,value in sorted(weak_missing.items())],
        'invalid_images':invalid,'full_build_compatibility_asserted':False}
output=args.output or project/('artifacts/native-dependency-inventory.json' if args.native_stage
    else 'artifacts/runtime-dependency-inventory.json')
output.write_text(json.dumps(report,indent=2)+'\n')
print(f'Visited {len(images)} Mach-O images; missing required: {len(missing)}, weak: {len(weak_missing)}, invalid: {len(invalid)}')
for key,value in sorted(missing.items()):print(key+' <- '+', '.join(sorted(value)))
