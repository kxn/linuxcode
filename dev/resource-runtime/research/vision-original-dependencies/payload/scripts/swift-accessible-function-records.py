#!/usr/bin/env python3
"""Read the typed __swift5_acfuncs table without guessing binary typeref headers.

swift-6.3.3 Metadata.h TargetAccessibleFunctionRecord and GenDecl.cpp emit
four relative pointers followed by AccessibleFunctionFlags (20 bytes).
Only local strings, types, environments and code/async descriptors are supported.
"""
import struct

def validate(read, sections):
    tables=[(start,size) for segment,name,start,size in sections
            if segment=='__TEXT' and name=='__swift5_acfuncs' and size]
    if not tables:return []
    if len(tables)!=1:raise ValueError('Multiple accessible-function tables')
    start,size=tables[0]
    if start%4 or size%20 or size>20*65536:
        raise ValueError('Invalid accessible-function table extent')
    def owner(address,length,names):
        return next(((base,count) for segment,name,base,count in sections
            if segment=='__TEXT' and name in names and base<=address and address+length<=base+count),None)
    records=[]
    for at in range(start,start+size,20):
        name_delta,env_delta,type_delta,function_delta,flags=struct.unpack('<4iI',read(at,20))
        if flags&~1:raise ValueError('Unsupported accessible-function flags')
        if not name_delta or not type_delta or not function_delta:
            raise ValueError('Null required accessible-function reference')
        name,env,type_ref,function=(at+name_delta,at+4+env_delta if env_delta else 0,
                                   at+8+type_delta,at+12+function_delta)
        name_section=owner(name,1,('__const','__cstring'))
        if not name_section:raise ValueError('Accessible-function name outside original strings')
        base,count=name_section
        payload=read(name,min(4096,base+count-name)).split(b'\0',1)
        if len(payload)!=2 or not payload[0]:raise ValueError('Unbounded accessible-function name')
        label=payload[0].decode('utf-8')
        if not owner(type_ref,1,('__swift5_typeref',)) or not read(type_ref,1)[0]:
            raise ValueError('Accessible-function type outside original typerefs')
        if env and (env%4 or not owner(env,4,('__swift5_typeref',))):
            raise ValueError('Accessible-function environment outside original typerefs')
        async_context_size=None
        if owner(function,1,('__text','__textcoal_nt')):
            code=function
        elif function%4==0 and owner(function,8,('__const',)):
            delta,async_context_size=struct.unpack('<iI',read(function,8))
            code=function+delta
            if not delta or not owner(code,1,('__text','__textcoal_nt')):
                raise ValueError('Accessible-function async code outside original text')
            if async_context_size<16 or async_context_size>1<<24 or async_context_size%8:
                raise ValueError('Unsupported accessible-function async context size')
        else:raise ValueError('Accessible-function entry outside original code/descriptors')
        records.append(dict(record=hex(at),name=label,environment=hex(env) if env else None,
            function_type=hex(type_ref),function=hex(function),code=hex(code),flags=flags,
            async_context_size=async_context_size))
    return records
