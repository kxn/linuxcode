#!/usr/bin/env python3
"""Independently decode the generated fixture's DER, without Apple code."""
from pathlib import Path

def decode(data):
    def node(offset,end):
        if offset+2>end:raise ValueError('Truncated DER header')
        tag,length=data[offset:offset+2];offset+=2
        if tag&31==31:raise ValueError('Unsupported high-tag encoding')
        if length&128:
            count=length&127
            if not count or count>8 or offset+count>end or not data[offset]:raise ValueError('Invalid DER length')
            length=int.from_bytes(data[offset:offset+count],'big');offset+=count
            if length<128:raise ValueError('Noncanonical DER length')
        stop=offset+length
        if stop>end:raise ValueError('DER value exceeds its container')
        if tag&32:
            children=[]
            while offset<stop:
                child,offset=node(offset,stop);children.append(child)
            if tag==0xb0:
                result={};previous=None
                for child_tag,pair in children:
                    if child_tag!=0x30 or len(pair)!=2 or pair[0][0]!=0x0c:raise ValueError('Invalid dictionary entry')
                    key=pair[0][1]
                    if previous is not None and key<=previous:raise ValueError('Unsorted or duplicate keys')
                    previous=key;result[key]=value(pair[1])
                payload=result
            else:payload=children
        elif tag==0x0c:payload=data[offset:stop].decode('utf-8')
        elif tag==1:
            if length!=1 or data[offset] not in (0,255):raise ValueError('Noncanonical DER boolean')
            payload=bool(data[offset])
        elif tag==2:
            raw=data[offset:stop]
            if not raw:raise ValueError('Empty DER integer')
            if len(raw)>1 and ((raw[0]==0 and raw[1]<128) or (raw[0]==255 and raw[1]>=128)):
                raise ValueError('Noncanonical DER integer')
            payload=int.from_bytes(raw,'big',signed=True)
        else:raise ValueError(f'Unsupported DER tag {tag:#x}')
        return (tag,payload),stop
    def value(item):
        tag,payload=item
        return [value(child) for child in payload] if tag==0x30 else payload
    root,end=node(0,len(data))
    if end!=len(data) or root[0]!=0x70 or len(root[1])!=2:raise ValueError('Invalid entitlement envelope')
    version,dictionary=root[1]
    if version!=(2,1) or dictionary[0]!=0xb0:raise ValueError('Unsupported entitlement format')
    return dictionary[1]

if __name__=='__main__':
    project=Path(__file__).resolve().parent.parent
    cases={'coreentitlements-probe.der':{'probe':True},
           'coreentitlements-nested.der':{'groups':['group.example.one','group.example.two'],'level':7,'probe':True}}
    for name,expected in cases.items():
        actual=decode((project/'artifacts'/name).read_bytes())
        if actual!=expected:raise SystemExit('Decoded entitlements differ from fixture input: '+name)
        if type(actual['probe']) is not bool:raise SystemExit('Boolean encoded with wrong ASN.1 type')
        print(name+': independent DER decode matches original dictionary')
