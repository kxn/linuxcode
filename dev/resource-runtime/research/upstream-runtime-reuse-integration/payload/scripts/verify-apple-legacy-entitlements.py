#!/usr/bin/env python3
"""Decode Apple's legacy SET-based entitlement format, separately from CE v1.

Apple's der_boolean.c and its regression encode true as 01, not ASN.1's FF.
This reader accepts those two true encodings only in this legacy grammar.
It does not relax the version-1 CoreEntitlements decoder.
"""
def decode(data):
    def node(at,end,depth=0):
        if depth>64 or at+2>end:raise ValueError('Truncated/excessively nested legacy DER')
        start=at;tag,length=data[at:at+2];at+=2
        if length&128:
            n=length&127
            if not n or n>4 or at+n>end or not data[at]:raise ValueError('Invalid legacy DER length')
            length=int.from_bytes(data[at:at+n],'big');at+=n
            if length<128:raise ValueError('Nonminimal legacy DER length')
        stop=at+length
        if stop>end:raise ValueError('Legacy DER crosses container')
        if tag in (0x30,0x31):
            children=[];encoded=[]
            while at<stop:
                child,next_at=node(at,stop,depth+1);children.append(child);encoded.append(data[at:next_at]);at=next_at
            if tag==0x31:
                if encoded!=sorted(encoded):raise ValueError('Unsorted legacy DER set')
                value={}
                for child in children:
                    if child[0]!=0x30 or len(child[1])!=2 or child[1][0][0]!=0x0c:raise ValueError('Invalid legacy dictionary pair')
                    key=child[1][0][1]
                    if key in value:raise ValueError('Duplicate legacy dictionary key')
                    value[key]=native(child[1][1])
            else:value=children
        elif tag==1:
            if length!=1 or data[at] not in (0,1,255):raise ValueError('Unsupported legacy boolean')
            value=data[at]!=0
        elif tag==2:
            raw=data[at:stop]
            if not raw or len(raw)>8:raise ValueError('Unsupported legacy integer')
            if len(raw)>1 and ((raw[0]==0 and raw[1]<128) or (raw[0]==255 and raw[1]>=128)):raise ValueError('Nonminimal legacy integer')
            value=int.from_bytes(raw,'big',signed=True)
        elif tag==0x0c:value=data[at:stop].decode('utf-8')
        elif tag==4:value=data[at:stop]
        else:raise ValueError('Unsupported legacy entitlement tag '+hex(tag))
        return (tag,value),stop
    def native(item):return [native(v) for v in item[1]] if item[0]==0x30 else item[1]
    root,end=node(0,len(data))
    if end!=len(data) or root[0]!=0x31:raise ValueError('Expected a complete legacy entitlement dictionary')
    return root[1]
