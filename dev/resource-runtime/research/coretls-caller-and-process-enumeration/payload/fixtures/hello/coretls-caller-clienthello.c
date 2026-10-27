#include <tls_handshake.h>
#include <tls_ciphersuites.h>
#include <CipherSuite.h>
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#define LOAD(name) __typeof__(&name) p_##name=(__typeof__(&name))dlsym(library,#name);assert(p_##name)
struct output { unsigned calls,alerts; size_t length; unsigned char bytes[8192]; };
static int write_message(void *context,const tls_buffer data,uint8_t type)
{
    struct output *out=context;
    if(type==21){out->alerts++;return 0;}
    assert(type==22 && out->length+data.length<=sizeof(out->bytes));
    memcpy(out->bytes+out->length,data.data,data.length);out->length+=data.length;out->calls++;return 0;
}
static int message(void *context,tls_handshake_message_t type){return 0;}
static void ready(void *context,bool write,bool value){assert(!value);}
static int protocol(void *context,tls_protocol_version version){return 0;}
static int timer(void *context,int attempt){return 0;}
static int empty(void *context){return 0;}
static unsigned u16(const unsigned char *p){return (p[0]<<8)|p[1];}
int main(int argc,char **argv)
{
    setbuf(stdout,NULL);assert(argc==2);void *library=dlopen("/usr/lib/libcoretls.dylib",RTLD_NOW|RTLD_LOCAL);if(!library)fprintf(stderr,"TLS_DLOPEN_ERROR %s\n",dlerror());assert(library);
    FILE *symbols=fopen(argv[1],"r");assert(symbols);char symbol[256];unsigned resolved=0;
    while(fgets(symbol,sizeof(symbol),symbols)){symbol[strcspn(symbol,"\r\n")]=0;assert(symbol[0]=='_' && dlsym(library,symbol+1));resolved++;}fclose(symbols);assert(resolved==301);
    LOAD(tls_handshake_create);LOAD(tls_handshake_create_for_caller);LOAD(tls_handshake_set_callbacks);LOAD(tls_handshake_set_min_protocol_version);LOAD(tls_handshake_set_max_protocol_version);LOAD(tls_handshake_set_ciphersuites);LOAD(tls_handshake_set_peer_hostname);LOAD(tls_handshake_negotiate);LOAD(tls_handshake_process);LOAD(tls_handshake_destroy);
    char long_label[1024];memset(long_label,'x',sizeof(long_label)-1);long_label[sizeof(long_label)-1]=0;
    const char *labels[]={NULL,"","linuxcode.client",long_label};
    for(unsigned n=0;n<5;n++){
        tls_handshake_t context=n==4?p_tls_handshake_create(false,false):p_tls_handshake_create_for_caller(false,false,labels[n]);assert(context);
        struct output out={0};tls_handshake_callbacks_t callbacks={0};callbacks.write=write_message;callbacks.message=message;callbacks.ready=ready;callbacks.set_protocol_version=protocol;callbacks.set_retransmit_timer=timer;callbacks.advance_write_cipher=empty;callbacks.advance_read_cipher=empty;callbacks.rollback_write_cipher=empty;
        assert(p_tls_handshake_set_callbacks(context,&callbacks,&out)==0);
        assert(p_tls_handshake_set_min_protocol_version(context,tls_protocol_version_TLS_1_2)==0);
        assert(p_tls_handshake_set_max_protocol_version(context,tls_protocol_version_TLS_1_2)==0);
        const uint16_t suite=TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256;assert(p_tls_handshake_set_ciphersuites(context,&suite,1)==0);
        assert(p_tls_handshake_set_peer_hostname(context,"localhost",9)==0);
        assert(p_tls_handshake_negotiate(context,NULL)==0 && out.calls>0 && out.length>42);
        assert(out.bytes[0]==1 && (((unsigned)out.bytes[1]<<16)|(out.bytes[2]<<8)|out.bytes[3])==out.length-4);
        assert(u16(out.bytes+4)==0x0303);size_t cursor=39+out.bytes[38];assert(cursor+2<=out.length);unsigned count=u16(out.bytes+cursor);cursor+=2;assert(count>=2 && !(count&1) && cursor+count<=out.length);
        bool found=false;for(unsigned i=0;i<count;i+=2)if(u16(out.bytes+cursor+i)==suite)found=true;assert(found);
        unsigned char malformed[]={2,0,0,0};tls_buffer data={sizeof(malformed),malformed};assert(p_tls_handshake_process(context,data,22)!=0);
        p_tls_handshake_destroy(context);
    }
    printf("CORETLS_PUBLIC_NAMESPACE_RESOLVED %u\n",resolved);puts("CORETLS_CALLER_AND_LEGACY_REAL_TLS12_CLIENTHELLO_AND_MALFORMED_REJECTION_OK");return 0;
}
