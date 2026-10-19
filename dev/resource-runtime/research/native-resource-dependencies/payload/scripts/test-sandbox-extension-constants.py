#!/usr/bin/env python3
"""Compare actual selected uint32 flag objects with the pinned original cache."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import runpy
import struct
import subprocess
import tempfile

root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--graphics-stage',required=True)
args=parser.parse_args()
folder=Path(tempfile.mkdtemp(prefix='sandbox-extension-constants-',dir=root/'runtime'))
cache=runpy.run_path(str(root/'scripts/dsc-image.py'),init_globals={
    'REFERENCE_CACHE_PATH':root/'runtime/fullsystem/intel-cache/dyld_shared_cache_x86_64h',
    'REFERENCE_LIBRARY_ROOT':root/'runtime/fullsystem-libraries'})
provider='/usr/lib/system/libsystem_sandbox.dylib'
names=['SANDBOX_EXTENSION_DEFAULT','SANDBOX_EXTENSION_CANONICAL','SANDBOX_EXTENSION_PREFIXMATCH',
    'SANDBOX_EXTENSION_NO_REPORT','SANDBOX_EXTENSION_NOFOLLOW','SANDBOX_EXTENSION_NOFOLLOW_ANY',
    'SANDBOX_EXTENSION_NO_STORAGE_CLASS','SANDBOX_EXTENSION_USER_INTENT','SANDBOX_EXTENSION_MACL_LEARNING']
values={name:struct.unpack('<I',cache['read'](cache['resolve'](provider,'_'+name),4))[0] for name in names}
source=folder/'test.c'
source.write_text('''#include <assert.h>
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(void) {
    setbuf(stdout,NULL);
    assert(!getenv("DISPLAY") && !getenv("WAYLAND_DISPLAY") && !getenv("XAUTHORITY"));
    struct { const char *name; uint32_t value; } cases[] = {
'''+',\n'.join('{'+json.dumps(name)+','+str(value)+'U}' for name,value in values.items())+'''};
    for (unsigned n=0;n<9;++n) {
        const uint32_t *address=dlsym(RTLD_DEFAULT,cases[n].name);
        assert(address && (uintptr_t)address%4==0 && *address==cases[n].value);
        if (n>=4) {
            Dl_info owner;assert(dladdr(address,&owner));
            assert(strstr(owner.dli_fname,"/coregraphics-native-") && strstr(owner.dli_fname,"/libDarlingSandboxExtensionConstants.dylib"));
        }
        printf("SANDBOX_EXTENSION_UINT32_OK %s %u\\n",cases[n].name,*address);
    }
    puts("SANDBOX_EXTENSION_CONSTANTS_NATIVE_OK 9");return 0;
}
''')
sdk=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
obj,binary=folder/'test.o',folder/'test'
subprocess.run(['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2','-c',str(source),'-o',str(obj)],check=True)
subprocess.run(['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-lSystem',str(obj),'-o',str(binary)],check=True)
module=runpy.run_path(str(root/'scripts/coregraphics-native-profile.py'))
p=module['profile'](graphics_stage=args.graphics_stage,include_resource_environment=False)
env=module['environment'](p)
for name in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(name,None)
command=p['command'][:-2]+['/usr/bin/env','-u','DISPLAY','-u','WAYLAND_DISPLAY','-u','XAUTHORITY',
    '/Volumes/SystemRoot/workspace/'+str(binary.relative_to(root))]
command[3]='60'
log=folder/'run.log'
with log.open('w') as out:result=subprocess.run(command,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
text=log.read_text();verified=result.returncode==0 and re.search(r'^SANDBOX_EXTENSION_CONSTANTS_NATIVE_OK 9$',text,re.M) is not None
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
record=dict(verified=verified,outer_status=result.returncode,command=command,values=values,
    new_objects=5,previous_objects_preserved=4,original_values_from_cache=True,
    original_provider_sha256=sha(root/('runtime/fullsystem-libraries'+provider)),
    new_policy_operations_implemented=False,GUI_required=False,
    files={str(p.relative_to(root)):sha(p) for p in [source,Path(__file__),binary,log,root/args.graphics_stage]})
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(text[-2000:]);print('EVIDENCE',folder/'result.json')
raise SystemExit(0 if verified else 1)
