#include <xpc/xpc.h>
#include <dlfcn.h>
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
int main(int argc,char **argv) {
 assert(argc==2);bool present=!strcmp(argv[1],"signed");
 xpc_object_t (*one)(const char*)=dlsym(RTLD_DEFAULT,"xpc_copy_entitlement_for_self");
 xpc_object_t (*all)(void)=dlsym(RTLD_DEFAULT,"xpc_copy_entitlements_for_self");assert(one && all);
 assert(!one(NULL) && !one("org.linuxcode.not-present"));
 xpc_object_t dictionary=all();
 if(!present){assert(!dictionary && !one("org.linuxcode.true"));puts("SELF_ENTITLEMENTS_ABSENT_NATIVE_OK");return 0;}
 assert(dictionary && xpc_get_type(dictionary)==XPC_TYPE_DICTIONARY);
 const char *names[]={"org.linuxcode.true","org.linuxcode.false"};
 for(unsigned i=0;i<2;++i){xpc_object_t v=one(names[i]);assert(v && xpc_get_type(v)==XPC_TYPE_BOOL && xpc_bool_get_value(v)==(i==0));xpc_release(v);}
 xpc_object_t v=one("org.linuxcode.string");assert(v && !strcmp(xpc_string_get_string_ptr(v),"original-signature-value"));xpc_release(v);
 v=one("org.linuxcode.number");assert(v && xpc_int64_get_value(v)==42);xpc_release(v);
 v=one("org.linuxcode.array");assert(v && xpc_array_get_count(v)==2 && !strcmp(xpc_array_get_string(v,0),"first") && xpc_array_get_bool(v,1));xpc_release(v);
 xpc_object_t nested=xpc_dictionary_get_value(dictionary,"org.linuxcode.nested");assert(nested && xpc_dictionary_get_int64(nested,"number")==7);xpc_dictionary_set_int64(nested,"number",99);xpc_release(dictionary);
 v=one("org.linuxcode.nested");assert(v && xpc_dictionary_get_int64(v,"number")==7);xpc_release(v);
 puts("SELF_ENTITLEMENTS_SIGNED_NATIVE_OK true false string integer array nested_dictionary fresh_return_values");return 0;
}
