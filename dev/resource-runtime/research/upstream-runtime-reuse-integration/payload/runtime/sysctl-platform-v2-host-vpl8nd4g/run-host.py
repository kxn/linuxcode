from pathlib import Path
import json,subprocess
root=Path.cwd();out=Path('/home/dl/linuxcode/runtime/sysctl-platform-v2-host-vpl8nd4g');report=json.loads((out/'compile-report.json').read_text());commands=[];objects=[]
for command in report['commands']:
 if not any(command[command.index('-c')+1].endswith('/'+n+'.c') for n in ['sysctl','sysctl_hw','sysctl_unspec']):continue
 c=list(command);c[c.index('-target')+1]='x86_64-unknown-linux-gnu';source=c[c.index('-c')+1];obj=out/('host-'+Path(source).stem+'.o');c[c.index('-o')+1]=str((root/obj).resolve());c+=['-D__APPLE__=1','-D__MACH__=1','-DTARGET_CPU_X86_64=1','-fsanitize=address,undefined','-fno-omit-frame-pointer','-O1'];commands.append(c)
 with (out/(obj.stem+'.compile.log')).open('w') as log:subprocess.run(c,check=True,stdout=log,stderr=subprocess.STDOUT)
 objects.append(obj)
c=list(commands[0]);c[c.index('-c')+1]=str((root/out/'test.c').resolve());c[c.index('-o')+1]=str((root/out/'test.o').resolve());commands.append(c)
with (out/'test.compile.log').open('w') as log:subprocess.run(c,check=True,stdout=log,stderr=subprocess.STDOUT)
objects.append(out/'test.o');c=['clang-19','-fsanitize=address,undefined','-c',str(out/'linux.c'),'-o',str(out/'linux.o')];commands.append(c);subprocess.run(c,check=True);objects.append(out/'linux.o')
c=['gcc','-fsanitize=address,undefined',*[str(x) for x in objects],'-o',str(out/'test')];commands.append(c);subprocess.run(c,check=True)
result=subprocess.run([str(out/'test')],capture_output=True,text=True);(out/'host.log').write_text(result.stdout+result.stderr);print(result.returncode,result.stdout,result.stderr)
report.update(host_commands=commands,host_exit=result.returncode,host_output=result.stdout,ASan_UBSan=True,host_boundary_tests='completed');(out/'host-report.json').write_text(json.dumps(report,indent=2)+'\n');assert result.returncode==0
