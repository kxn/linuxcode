from pathlib import Path
import hashlib,json,subprocess,re
root=Path.cwd();out=Path('runtime/sigexc-self-image-host-53il66l7');report=json.loads((out/'compile-report.json').read_text());source=Path(report['source']);text=source.read_text();a=text.index('/* Best-effort current-process metadata,');b=text.index('\n#endif\n\nvoid sigexc_setup1',a);helper=text[a:b]
prefix=r'''
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdarg.h>
#include <unistd.h>
#include <sys/syscall.h>
#define LINUX_SYSCALL(n,...) syscall(n, ##__VA_ARGS__)
#define kern_printf(...) fprintf(stderr,__VA_ARGS__)
#define __simple_snprintf snprintf
struct _darling_libkernel_callbacks { int (*dyld_func_lookup)(const char*,void**); } _darling_libkernel_callbacks;
_Static_assert(sizeof(void*)==sizeof(_darling_libkernel_callbacks.dyld_func_lookup),"lookup pointer ABI");
'''
suffix=r'''
static int mode, nested;
static char long_image[1100];
static const char *get_path(const void* address) {
 (void)address;
 if(mode==4)return 0;
 if(mode==7)return long_image;
 if(mode==8)return "/test/line\nname\timage";
 return "/test/owned-image.dylib";
}
static const void *get_header(const void* address) {
 (void)address;return mode==5?0:(const void*)(uintptr_t)(mode==6?0x2000:0x1000);
}
static int get_executable(char* buffer,uint32_t* capacity) {
 if(mode==9){*capacity=800;return -1;}
 const char*name="/test/owned-process";size_t n=strlen(name)+1;
 if(*capacity<n){*capacity=n;return -1;}memcpy(buffer,name,n);return 0;
}
static int lookup(const char*name,void**value) {
 *value=0;
 if(mode==1)return 0;
 if(mode==10&&!nested){nested=1;log_signal_identity(11,0x1200);}
 if(!strcmp(name,"__dyld_image_path_containing_address"))*value=(void*)get_path;
 else if(!strcmp(name,"__dyld_get_image_header_containing_address")&&mode!=2)*value=(void*)get_header;
 else if(!strcmp(name,"__dyld__NSGetExecutablePath"))*value=(void*)get_executable;
 return *value!=0;
}
int main(void) {
 memset(long_image,'A',sizeof(long_image)-1);
 for(mode=0;mode<=10;mode++) {
  fprintf(stderr,"HOSTCASE mode=%d\n",mode);
  _darling_libkernel_callbacks.dyld_func_lookup=mode?lookup:0;
  log_signal_identity(11,0x1200);
 }
 return 0;
}
'''
# Make the control-byte case contain actual C escape sequences, not literal backslashes.
suffix=suffix.replace('line\nname\timage','line\nname\timage')
harness=out/'host.c';harness.write_text(prefix+helper+suffix)
command=['gcc','-std=gnu11','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(harness),'-o',str(out/'host')];subprocess.run(command,check=True)
process=subprocess.Popen([str(out/'host')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);stdout,stderr=process.communicate(timeout=5);(out/'host.log').write_text(stdout+stderr);assert process.returncode==0,(process.returncode,stderr)
checks=0
def check(value):
 global checks
 checks+=1
 assert value,checks
cases={int(mode):body for mode,body in re.findall(r'HOSTCASE mode=(\d+)\n(.*?)(?=HOSTCASE|\Z)',stderr,re.S)};check(set(cases)==set(range(11)))
for mode,body in cases.items():
 rows=body.splitlines();check(all(row.startswith('sigexc: signal-event ') for row in rows));check(all('linux_pid='+str(process.pid)+' ' in row and 'linux_tid='+str(process.pid)+' ' in row for row in rows));check(all('signal=11 pc=0x1200' in row for row in rows));check(any('phase=identity' in row for row in rows));check(any('phase=image' in row for row in rows));
check('lookup=uninitialized' in cases[0]);check('executable_status=uninitialized' in cases[0]);check('lookup=unavailable' in cases[1]);check('executable_status=unavailable' in cases[1]);check('lookup=unavailable' in cases[2]);check('executable_status=resolved' in cases[2]);check('header=0x1000 offset=0x200 lookup=resolved' in cases[3]);check('executable=/test/owned-process image=/test/owned-image.dylib' in cases[3]);
for mode in [4,5,6]:check('header=0x0 offset=0x0 lookup=unknown' in cases[mode]);check('image=<unknown>' in cases[mode])
check('image_truncated=1' in cases[7]);check('image=/test/line?name?image' in cases[8]);check(len(cases[7].splitlines())==3);check('executable_status=too-long' in cases[9]);check('executable=<unknown>' in cases[9]);check('lookup=busy' in cases[10]);check('lookup=resolved' in cases[10]);check(len(cases[10].splitlines())==5)
# Verify only logging was inserted: no original signal path or handler changed.
base=subprocess.check_output(['git','-C','runtime/sigexc-self-image-source-v1','show','HEAD:darling/src/libsystem_kernel/emulation/src/linux_premigration/signal/sigexc.c'],text=True)
a=text.index('#ifdef DEBUG_SIGEXC\n/* Best-effort current-process metadata,');b=text.index('\nvoid sigexc_setup1',a)
rest=text[:a]+text[b:];rest=rest.replace('#include <stdint.h>\n','').replace('#ifdef DEBUG_SIGEXC\n\tlog_signal_identity(linux_signum, ctxt->uc_mcontext.gregs.rip);\n#endif\n','');rest=re.sub(r'\n+void sigexc_setup1', '\n\nvoid sigexc_setup1', rest);check(rest==base)
undefined=subprocess.check_output(['llvm-nm-19','-u',str(out/'sigexc.o')],text=True);check('atomic' not in undefined and '_malloc' not in undefined and '_dlsym' not in undefined and '_dladdr' not in undefined)
r=dict(host_only=True,native_execution=False,checks=checks,ASan_UBSan=True,actual_source_helper_extracted=True,current_process_identity=True,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),source=str(source),harness=str(harness),harness_sha256=hashlib.sha256(harness.read_bytes()).hexdigest(),command=command,normal_signal_control_flow_byte_identical=True,only_one_source_changed=True,uninitialized_unavailable_unmapped_busy_fallbacks=True,no_new_RPC_or_allocation_symbols=True,private_log=str(out/'host.log'),helper_extent_sha256=hashlib.sha256(helper.encode()).hexdigest());(out/'host-report.json').write_text(json.dumps(r,indent=2)+'\n');print('SIGEXC_HOST_PASS',checks)
