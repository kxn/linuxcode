#!/usr/bin/env python3
"""Build pinned zsign as a private static ELF tool for Darwin-to-Linux exec."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,subprocess
r=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',default='runtime/zsign-static-source');args=parser.parse_args()
build=(r/args.output_dir).resolve();assert build.is_relative_to((r/'runtime').resolve()) and not build.exists();build.mkdir(parents=True)
pin=json.loads((r/'config/zsign-source.json').read_text());source=r/'vendor/zsign'
if not source.exists():
 subprocess.run(['git','clone','--no-checkout',pin['repository'],str(source)],check=True)
 subprocess.run(['git','-C',str(source),'checkout','--detach',pin['revision']],check=True)
assert subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()==pin['revision'];assert not subprocess.check_output(['git','-C',str(source),'diff','HEAD','--','src','build/linux'])
libs=subprocess.check_output(['pkg-config','--static','--libs','openssl'],text=True).strip();command=['make','-C',str(source/'build/linux'),'-j8','BINDIR='+str(build),'OBJDIR='+str(build/'objects'),'CXX=g++ -static','OPENSSL_LIB='+libs]
log=build/'build.log'
with log.open('w') as out:subprocess.run(command,stdout=out,stderr=subprocess.STDOUT,check=True)
binary=build/'zsign';headers=subprocess.check_output(['readelf','-lW',str(binary)],text=True);assert 'INTERP' not in headers
version=subprocess.check_output([str(binary),'--version'],text=True).strip();sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
tracked=subprocess.check_output(['git','-C',str(source),'ls-files','src','build/linux'],text=True).splitlines()
record=dict(checked_at=datetime.now(timezone.utc).isoformat(),source=pin,command=command,static_ELF_verified=True,binary=str(binary.relative_to(r)),binary_sha256=sha(binary),version=version,log=str(log.relative_to(r)),log_sha256=sha(log),source_files={name:sha(source/name) for name in tracked},build_driver_sha256=sha(__file__),installed=False,certificate_or_device_trust_verified=False)
(build/'build.json').write_text(json.dumps(record,indent=2)+'\n');print(build/'build.json')
