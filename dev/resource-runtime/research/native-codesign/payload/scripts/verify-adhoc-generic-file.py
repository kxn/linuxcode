#!/usr/bin/env python3
"""Independently check ad-hoc signatures stored as Darwin inode attributes.

The Linux representation uses user.com.apple.cs.* attributes. This does not
evaluate certificate trust, CMS, requirements semantics or execution policy.
"""
from pathlib import Path
import hashlib,os,plistlib,struct
def verify(path):
    path=Path(path);content=path.read_bytes();prefix='user.com.apple.cs.'
    names={n[len(prefix):]:os.getxattr(path,n) for n in os.listxattr(path) if n.startswith(prefix)}
    assert not names.get('CodeSignature'), 'nonempty CMS is outside the ad-hoc scope'
    directories=[('CodeDirectory',names['CodeDirectory'])]+sorted((n,b) for n,b in names.items() if n.startswith('CodeRequirements-'))
    results=[];slots={2:'CodeRequirements',3:'CodeResources',5:'CodeEntitlements',7:'CodeEntitlementsDER'}
    for name,cd in directories:
        assert len(cd)>=44
        magic,length,version,flags,hash_at,identifier,special,pages,limit=struct.unpack_from('>9I',cd)
        hash_size,hash_type,platform,page_exp=struct.unpack_from('>4B',cd,36)
        assert magic==0xfade0c02 and length==len(cd) and version<=0x20600 and flags&2
        assert limit==len(content) and hash_type in (1,2) and hash_size=={1:20,2:32}[hash_type]
        assert page_exp in (0,12,14)
        # A zero exponent means one indefinite page in Apple's generic format.
        page_size=max(limit,1) if page_exp==0 else 1<<page_exp
        assert pages==(limit+page_size-1)//page_size
        assert hash_at>=special*hash_size and hash_at+pages*hash_size<=len(cd)
        digest=lambda b:hashlib.new('sha1' if hash_type==1 else 'sha256',b).digest()
        for i in range(pages):assert digest(content[i*page_size:min((i+1)*page_size,limit)])==cd[hash_at+i*hash_size:hash_at+(i+1)*hash_size],'generic code page hash mismatch'
        for i in range(1,special+1):
            stored=cd[hash_at-i*hash_size:hash_at-(i-1)*hash_size]
            if stored==bytes(hash_size):continue
            assert i in slots and slots[i] in names,'unsupported generic special slot'
            assert digest(names[slots[i]])==stored,'generic special slot hash mismatch'
        end=cd.index(0,identifier);label=cd[identifier:end].decode('utf-8')
        results.append(dict(attribute=name,code_pages=pages,special_slots=special,hash_algorithm='sha1' if hash_type==1 else 'sha256',identifier=label))
    entitlements=None
    if 'CodeEntitlements' in names:
        b=names['CodeEntitlements'];assert struct.unpack_from('>II',b)==(0xfade7171,len(b));entitlements=plistlib.loads(b[8:]);assert isinstance(entitlements,dict)
    return dict(verified=True,directories=results,entitlements=entitlements,DER_entitlements_present='CodeEntitlementsDER' in names,certificate_or_device_trust_verified=False)
if __name__=='__main__':
    import argparse,json
    a=argparse.ArgumentParser();a.add_argument('path');args=a.parse_args();print(json.dumps(verify(args.path),indent=2))
