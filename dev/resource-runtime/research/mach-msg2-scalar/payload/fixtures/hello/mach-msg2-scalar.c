#include <dlfcn.h>
#include <mach/mach.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
typedef mach_msg_return_t (*msg2_fn)(void*,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t);
#define MQ (1ull<<34)
#define KO (1ull<<33)
#define ANY (1ull<<35)
#define BAD_OPTIONS 0x10000013
static msg2_fn msg2;static int checks;
#define CHECK(v) do {++checks;if(!(v)){printf("MSG2_FAILED %d %s\n",__LINE__,#v);return 13;}} while(0)
static uint64_t pack(uint32_t a,uint32_t b){return ((uint64_t)b<<32)|a;}
struct payload {mach_msg_header_t h;uint32_t value,extra;};
static mach_msg_return_t send2(void *p,uint64_t flags,uint32_t size,mach_port_t port,int id) {
 return msg2(p,flags|MACH_SEND_MSG,pack(MACH_MSGH_BITS(MACH_MSG_TYPE_COPY_SEND,0),size),pack(port,0),pack(0,id),0,0,0);
}
int main(int argc,char **argv) {
 if(argc!=2)return 10;msg2=dlsym(RTLD_DEFAULT,"mach_msg2_internal");if(!msg2){puts("MSG2_MISSING");return 12;}
 Dl_info owner;CHECK(dladdr((void*)msg2,&owner));CHECK(strstr(owner.dli_fname,"libsystem_kernel.dylib"));printf("MSG2_PROVIDER %s\n",owner.dli_fname);
 mach_port_t port=MACH_PORT_NULL;CHECK(mach_port_allocate(mach_task_self(),MACH_PORT_RIGHT_RECEIVE,&port)==KERN_SUCCESS);CHECK(mach_port_insert_right(mach_task_self(),port,port,MACH_MSG_TYPE_MAKE_SEND)==KERN_SUCCESS);
 struct payload *out=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_ANON|MAP_PRIVATE,-1,0);CHECK(out!=MAP_FAILED);out->value=0x12345678;out->extra=0x87654321;CHECK(mprotect(out,4096,PROT_READ)==0);
 for(int i=0;i<16;++i) {
  CHECK(send2(out,MQ,sizeof(*out),port,700+i)==MACH_MSG_SUCCESS);
  struct {struct payload p;mach_msg_max_trailer_t trailer;} in={0};
  CHECK(mach_msg(&in.p.h,MACH_RCV_MSG|MACH_RCV_TIMEOUT,0,sizeof(in),port,1000,0)==MACH_MSG_SUCCESS);
  CHECK(in.p.h.msgh_id==700+i);CHECK(in.p.value==out->value);CHECK(in.p.extra==out->extra);
 }
 CHECK(out->h.msgh_bits==0 && out->h.msgh_remote_port==0); /* Captured header, no writes into read-only buffer. */
 CHECK(send2(out,KO,sizeof(*out),port,900)==BAD_OPTIONS);
 CHECK(send2(out,MQ|KO,sizeof(*out),port,900)==BAD_OPTIONS);
 CHECK(send2(out,0,sizeof(*out),port,900)==BAD_OPTIONS);
 CHECK(send2(out,MQ|(1ull<<50),sizeof(*out),port,900)==BAD_OPTIONS);
 CHECK(send2(out,MQ|(1ull<<32),sizeof(*out),port,900)==BAD_OPTIONS); /* Explicitly unsupported vector backend. */
 CHECK(send2((void*)1,MQ,sizeof(*out),port,900)==MACH_SEND_INVALID_DATA);
 CHECK(send2(out,MQ,4,port,900)==MACH_SEND_MSG_TOO_SMALL);
 CHECK(send2(out,KO,sizeof(*out),MACH_PORT_NULL,900)==MACH_SEND_INVALID_DEST);
 struct {struct payload p;mach_msg_max_trailer_t trailer;} in={0};
 CHECK(msg2(&in,MACH_RCV_MSG|MACH_RCV_TIMEOUT,0,0,0,pack(0,port),sizeof(in),1)==MACH_RCV_TIMED_OUT);
 /* New send -> new receive; the old API also remains independently exercised. */
 CHECK(send2(out,ANY,sizeof(*out),port,901)==MACH_MSG_SUCCESS);
 CHECK(msg2(&in,MACH_RCV_MSG|MACH_RCV_TIMEOUT,0,0,0,pack(0,port),sizeof(in),1000)==MACH_MSG_SUCCESS);
 CHECK(in.p.h.msgh_id==901 && in.p.value==out->value);
 /* Captured descriptor count overrides stale user-memory header/body data. */
 struct {mach_msg_base_t base;mach_msg_port_descriptor_t descriptor;} complex={0};
 complex.base.body.msgh_descriptor_count=99;
 complex.descriptor.name=port;complex.descriptor.disposition=MACH_MSG_TYPE_COPY_SEND;complex.descriptor.type=MACH_MSG_PORT_DESCRIPTOR;
 CHECK(msg2(&complex,MQ|MACH_SEND_MSG,pack(MACH_MSGH_BITS_COMPLEX|MACH_MSGH_BITS(MACH_MSG_TYPE_COPY_SEND,0),sizeof(complex)),pack(port,0),pack(0,902),pack(1,0),0,0)==MACH_MSG_SUCCESS);
 struct {mach_msg_base_t base;mach_msg_port_descriptor_t descriptor;mach_msg_max_trailer_t trailer;} received={0};
 CHECK(mach_msg(&received.base.header,MACH_RCV_MSG|MACH_RCV_TIMEOUT,0,sizeof(received),port,1000,0)==MACH_MSG_SUCCESS);
 CHECK(received.base.body.msgh_descriptor_count==1);CHECK(received.descriptor.name==port);
 CHECK(mach_port_deallocate(mach_task_self(),received.descriptor.name)==KERN_SUCCESS);
 /* Combined request/reply to the real kernel host MIG subsystem (message 200). */
 mach_port_t reply=MACH_PORT_NULL;CHECK(mach_port_allocate(mach_task_self(),MACH_PORT_RIGHT_RECEIVE,&reply)==KERN_SUCCESS);
 mach_port_t host=mach_host_self();
 struct request {mach_msg_header_t h;NDR_record_t ndr;host_flavor_t flavor;mach_msg_type_number_t count;};
 struct response {mach_msg_header_t h;NDR_record_t ndr;kern_return_t status;mach_msg_type_number_t count;integer_t data[68];mach_msg_max_trailer_t trailer;};
 union {struct request request;struct response response;} call={0};
 call.request.ndr=NDR_record;call.request.flavor=HOST_BASIC_INFO;call.request.count=HOST_BASIC_INFO_COUNT;
 uint32_t bits=MACH_MSGH_BITS(MACH_MSG_TYPE_COPY_SEND,MACH_MSG_TYPE_MAKE_SEND_ONCE);
 CHECK(msg2(&call,KO|MACH_SEND_MSG|MACH_RCV_MSG|MACH_RCV_TIMEOUT,pack(bits,sizeof(struct request)),pack(host,reply),pack(0,200),pack(0,reply),sizeof(call),1000)==MACH_MSG_SUCCESS);
 CHECK(call.response.h.msgh_id==300);CHECK(call.response.status==KERN_SUCCESS);CHECK(call.response.count==HOST_BASIC_INFO_COUNT);
 host_basic_info_data_t old_info={0};mach_msg_type_number_t count=HOST_BASIC_INFO_COUNT;
 CHECK(host_info(host,HOST_BASIC_INFO,(host_info_t)&old_info,&count)==KERN_SUCCESS);
 host_basic_info_t new_info=(host_basic_info_t)call.response.data;CHECK(new_info->avail_cpus==old_info.avail_cpus && new_info->max_mem==old_info.max_mem);
 CHECK(mach_port_destroy(mach_task_self(),reply)==KERN_SUCCESS);CHECK(mach_port_deallocate(mach_task_self(),host)==KERN_SUCCESS);
 CHECK(munmap(out,4096)==0);CHECK(mach_port_destroy(mach_task_self(),port)==KERN_SUCCESS);
 if(checks!=atoi(argv[1])){printf("MSG2_COUNT_MISMATCH %d\n",checks);return 15;}
 printf("MSG2_SCALAR_CAPTURED_READONLY_TRANSPORT_AND_ERRORS_OK %d\n",checks);return 0;
}
