"""Validate the ObjC objects in non-resilient Swift singleton class metadata.

Swift ABI Metadata.h TargetSingletonMetadataInitialization uses IncompleteMetadata
for a class without resilient ancestry, and ResilientPattern otherwise. The
former is a real class metadata object, even when absent from __objc_classlist.
"""
import struct


def validate(read,pointer,sections,descriptor,metadata):
    def contains(address,size):
        return any(start<=address and address+size<=start+length
                   for segment,name,start,length in sections)
    def string(address):
        data=read(address,512)
        assert b'\0' in data
        value=data.split(b'\0')[0]
        assert value
        return value.decode('utf-8')
    assert contains(descriptor,44) and contains(metadata,80)
    flags=struct.unpack('<I',read(descriptor,4))[0]
    specific=flags>>16
    assert flags&31==16 and not flags&128
    assert specific&3==1 and not specific&0x2000
    assert metadata%8==0 and pointer(metadata+64)==descriptor
    bits=pointer(metadata+32)
    assert bits&7==2, 'Expected stable Swift ObjC class data'
    ro=bits&~7
    meta=pointer(metadata)
    assert meta!=metadata and meta%8==0 and contains(meta,40)
    meta_ro=pointer(meta+32)&~7
    assert contains(ro,72) and contains(meta_ro,72) and ro!=meta_ro
    class_flags=struct.unpack('<I',read(ro,4))[0]
    meta_flags=struct.unpack('<I',read(meta_ro,4))[0]
    assert not class_flags&1 and meta_flags&1
    name=string(pointer(ro+24))
    assert string(pointer(meta_ro+24))==name
    return dict(kind='non-resilient-singleton-IncompleteMetadata',
                descriptor=hex(descriptor),metadata=hex(metadata),metaclass=hex(meta),
                class_ro=hex(ro),metaclass_ro=hex(meta_ro),objc_name=name,
                original_class_data_flags=bits&7,
                metadata_descriptor_identity_verified=True)
