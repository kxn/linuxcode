#!/usr/bin/env python3
"""Compare original SIMD routines with Linux scalar math and exact rational inverses."""
from fractions import Fraction
from pathlib import Path
import argparse
import hashlib
import json
import math
import random
import re
import runpy
import struct
import subprocess
import tempfile

root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--graphics-stage')
parser.add_argument('--scalar-log2-only',action='store_true',help='Test scalar log2 with every exact binary power instead of repeating SIMD tests')
parser.add_argument('--runtime-stage',default='artifacts/private-procfs-auditsession110-stage.json')
parser.add_argument('--configuration',default='config/direct-resource-tool-environment-v154.json')
parser.add_argument('--scalar-library',help='Optional private candidate math library; otherwise test the selected runtime provider')
parser.add_argument('--expect-scalar-failure',action='store_true')
parser.add_argument('--scalar-family',action='store_true',help='Also exercise nonpowers, rounding modes, float/long-double powers and record special-value flags')
args=parser.parse_args()
folder=Path(tempfile.mkdtemp(prefix='original-simd-math-test-',dir=root/'runtime'))
if args.scalar_log2_only:
    source=root/'fixtures/hello/libm-log2-powers.c'
    sdk=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
    obj,binary=folder/'scalar.o',folder/'scalar'
    build_commands=[['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2','-fno-builtin','-c',str(source),'-o',str(obj)],
                    ['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-lSystem',str(obj),'-o',str(binary)]]
    for command in build_commands:subprocess.run(command,check=True)
    module=runpy.run_path(str(root/'scripts/direct-resource-tool-runtime-profile.py'))
    profile=module['profile'](stage=args.runtime_stage,configuration=args.configuration)
    original=root/'runtime/native-simd-math-v1/libraries/libDarlingNativeSIMDMath.dylib'
    guest=lambda p:'/Volumes/SystemRoot/workspace/'+str(p.relative_to(root))
    candidate=(root/args.scalar_library).resolve(strict=True) if args.scalar_library else None
    command=list(profile['command'][:-2])
    if candidate:
        index=next(i for i,value in enumerate(command) if value.startswith('DYLD_LIBRARY_PATH='))
        command[index]='DYLD_LIBRARY_PATH='+guest(candidate.parent)+':'+command[index].split('=',1)[1]
    command += [guest(binary),guest(original),guest(candidate) if candidate else 'default']+(['family'] if args.scalar_family else []);command[3]='30'
    env=module['environment'](profile)
    for name in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']:env.pop(name,None)
    log=folder/'scalar.log'
    with log.open('w') as out:result=subprocess.run(command,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT)
    text=log.read_text();counts=re.findall(r'^LOG2_POWERS cases=2098 failures=(\d+) reference_failures=(\d+)$',text,re.M)
    verified=(len(counts)==1 and counts[0][1]=='0' and
              (result.returncode==1 and int(counts[0][0])>0 if args.expect_scalar_failure else result.returncode==0 and counts[0][0]=='0'))
    if args.scalar_family:verified=verified and re.search(r'^LOG2_FAMILY cases=\d+ failures=0 ',text,re.M) is not None
    owners=dict(re.findall(r'^(ACTUAL|REFERENCE)_OWNER (.+)$',text,re.M))
    independent_owners=set(owners)=={'ACTUAL','REFERENCE'} and owners['ACTUAL']!=owners['REFERENCE']
    verified=verified and independent_owners
    family_match=re.search(r'^LOG2_FAMILY cases=(\d+) failures=(\d+) mainline_max_ulp=(\d+) ',text,re.M)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    record=dict(verified=verified,expected_failure=args.expect_scalar_failure,cases=2098,counts=counts,outer_status=result.returncode,
                command=command,build_commands=build_commands,runtime_stage=args.runtime_stage,configuration=args.configuration,
                files={str(p.relative_to(root)):sha(p) for p in [source,Path(__file__),original,binary,log,*([candidate] if candidate else [])]},
                original_apple_scalar_reference=True,independent_function_owners=independent_owners,function_owners=owners,
                family_counts=dict(cases=int(family_match[1]),failures=int(family_match[2]),mainline_max_ulp=int(family_match[3])) if family_match else None,
                full_goal_complete=False)
    (folder/'result.json').write_text(json.dumps(record,indent=2)+'\n')
    print(text);print('EVIDENCE',folder/'result.json');raise SystemExit(0 if verified else 1)
assert args.graphics_stage,'--graphics-stage is required for the SIMD suite'
rng=random.Random(20261019)
matrix_inputs=[[[int(i==j) for j in range(3)] for i in range(3)]]
for _ in range(128):
    matrix_inputs.append([[rng.randint(12,24) if i==j else rng.randint(-3,3) for j in range(3)] for i in range(3)])
matrix_records=[]
for matrix in matrix_inputs:
    work=[[Fraction(value) for value in row]+[Fraction(int(i==j)) for j in range(3)] for i,row in enumerate(matrix)]
    for col in range(3):
        pivot=work[col][col];assert pivot
        work[col]=[value/pivot for value in work[col]]
        for row in range(3):
            if row!=col:
                scale=work[row][col];work[row]=[a-scale*b for a,b in zip(work[row],work[col])]
    matrix_records.append({'input':sum(matrix,[]),'inverse':sum([[float(x) for x in row[3:]] for row in work],[])})
round_float=lambda x:struct.unpack('<f',struct.pack('<f',x))[0]
vectors=[]
functions=[math.exp,math.exp2,math.log,math.log2,math.sin,math.pow]
for function in range(6):
    inputs=[]
    for n in range(64):
        if function in (0,1):x=round_float(rng.uniform(-80,80));y=0
        elif function in (2,3):x=round_float(2.0**rng.uniform(-120,120));y=0
        elif function==4:x=round_float(rng.uniform(-1000,1000));y=0
        else:x=round_float(2.0**rng.uniform(-8,8));y=round_float(rng.uniform(-8,8))
        inputs.append((x,y))
    for at in range(0,len(inputs),4):
        group=inputs[at:at+4]
        expected=[round_float(functions[function](x,y) if function==5 else functions[function](x)) for x,y in group]
        vectors.append({'function':function,'x':[x for x,y in group],'y':[y for x,y in group],'expected':expected})
special=[(0,[-math.inf,math.inf,math.nan,-0.0],[0,0,0,0],[0,math.inf,math.nan,1]),
         (1,[-math.inf,math.inf,math.nan,0],[0,0,0,0],[0,math.inf,math.nan,1]),
         (2,[0,-1,math.inf,math.nan],[0,0,0,0],[-math.inf,math.nan,math.inf,math.nan]),
         (3,[1,0,-1,math.inf],[0,0,0,0],[0,-math.inf,math.nan,math.inf]),
         (4,[-0.0,0,math.nan,math.inf],[0,0,0,0],[-0.0,0,math.nan,math.nan]),
         (5,[0,-2,-2,math.nan],[2,3,0.5,0],[0,-8,math.nan,1])]
for fn,x,y,expected in special:vectors.append(dict(function=fn,x=x,y=y,expected=expected))
def literal(value):
    if math.isnan(value):return 'NAN'
    if math.isinf(value):return '-INFINITY' if value<0 else 'INFINITY'
    return float(value).hex()
array=lambda values:'{'+','.join(literal(x) for x in values)+'}'
header='struct matrix_case { float input[9]; double inverse[9]; };\nstatic const struct matrix_case matrices[] = {\n'
header+=',\n'.join('{'+array(row['input'])+','+array(row['inverse'])+'}' for row in matrix_records)+'\n};\n'
header+='struct vector_case { unsigned function; float x[4],y[4],expected[4]; };\nstatic const struct vector_case vectors[] = {\n'
header+=',\n'.join('{'+str(row['function'])+','+','.join(array(row[k]) for k in ['x','y','expected'])+'}' for row in vectors)+'\n};\n'
(folder/'oracle.h').write_text(header)
source=root/'fixtures/hello/original-simd-math.c'
sdk=root/'runtime/state/prefix/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
obj,binary=folder/'test.o',folder/'test'
subprocess.run(['clang-19','-target','x86_64-apple-macos11','-isysroot',str(sdk),'-O2','-I',str(folder),'-c',str(source),'-o',str(obj)],check=True)
subprocess.run(['ld64.lld-19','-arch','x86_64','-platform_version','macos','11','11','-syslibroot',str(sdk),'-lSystem',str(obj),'-o',str(binary)],check=True)
module=runpy.run_path(str(root/'scripts/coregraphics-native-profile.py'))
p=module['profile'](graphics_stage=args.graphics_stage,include_resource_environment=False)
env=module['environment'](p)
gui=['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY']
for name in gui:env.pop(name,None)
command=p['command'][:-2]+['/usr/bin/env',*[part for name in gui for part in ('-u',name)],'/Volumes/SystemRoot/workspace/'+str(binary.relative_to(root))]
command[3]='60'
log=folder/'run.log'
with log.open('w') as stream:result=subprocess.run(command,cwd=root,env=env,stdout=stream,stderr=subprocess.STDOUT)
text=log.read_text()
markers=[f'ORIGINAL_SIMD_MATH_MATRIX_ORACLE_OK {len(matrix_records)}',f'ORIGINAL_SIMD_MATH_VECTOR_ORACLE_OK {len(vectors)*4}','ORIGINAL_SIMD_MATH_OWNERS_AND_HEADLESS_OK']
numeric_verified=result.returncode==0 and all(re.search('^'+re.escape(marker)+'$',text,re.M) for marker in markers)
zero_counts=re.findall(r'^ORIGINAL_SIMD_MATH_SIGNED_ZERO_DIFFERENCES (\d+)$',text,re.M)
verified=numeric_verified and zero_counts==['0']
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
files=[source,Path(__file__),folder/'oracle.h',binary,log,root/args.graphics_stage]
record=dict(verified=bool(verified),numeric_values_verified=bool(numeric_verified),
    signed_zero_differences=int(zero_counts[0]) if len(zero_counts)==1 else None,
    scalar_bitwise_equivalence_verified=False,outer_status=result.returncode,command=command,
    graphics_stage=args.graphics_stage,exact_rational_matrix_cases=len(matrix_records),Linux_scalar_vector_lanes=len(vectors)*4,
    vector_tolerance_ULP=8,original_implementation_owners_required=True,gui_environment_removed=gui,
    files={str(p.relative_to(root)):sha(p) for p in files},full_resource_compilation_verified=False)
(folder/'result.json').write_text(json.dumps(record,indent=2)+'\n')
print(text[-3000:]);print('EVIDENCE',folder/'result.json')
raise SystemExit(0 if verified else 1)
