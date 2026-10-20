"""Read stopped DVT function-assertion parameters without inferior calls."""
from pathlib import Path
exec(Path('scripts/gdb-dvt-assertion-arguments.py').read_text().split('regs={n:')[0])
regs={n:int(gdb.parse_and_eval('$'+n)) for n in ['rdi','rsi','rdx','rcx','r8','r9','rsp','rip']}
print('DVT_FUNCTION_REGISTERS',json.dumps({k:hex(v) for k,v in regs.items()}))
print('DVT_FUNCTION_LINE',regs['r8'])
for ptr,label in [(regs['rdx'],'function'),(regs['rcx'],'filename'),(regs['r9'],'signature'),(u64(regs['rsp']+8),'message-format')]:object_info(ptr,label)
try:
 va=u64(regs['rsp']+16);gp,fp,overflow,save=struct.unpack('<IIQQ',memory(va,24));print('DVT_FUNCTION_VA_LIST',hex(va),gp,fp,hex(overflow),hex(save))
 for i in range(8):
  if gp<48:arg=u64(save+gp);gp+=8
  else:arg=u64(overflow);overflow+=8
  object_info(arg,'argument-'+str(i))
except Exception as e:print('DVT_FUNCTION_VA_LIST_READ_FAILED',str(e))
handled=0
while queue and handled<96:
 p,label=queue.pop(0);object_info(p,label);handled+=1
