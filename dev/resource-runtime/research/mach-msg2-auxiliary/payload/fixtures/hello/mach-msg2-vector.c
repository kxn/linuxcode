#include <dlfcn.h>
#include <mach/mach.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#define CHECK(v) do{checks++;if(!(v)){printf("MSG2_VECTOR_FAILED line=%d %s\n",__LINE__,#v);return 1;}}while(0)
#define VECTOR (1ull<<32)
#define MQ (1ull<<34)
#define KO (1ull<<33)
#define BAD_OPTIONS 0x10000013
#define BAD_RECEIVE 0x10004013
struct vector{uint64_t data,rcv;uint32_t send_size,rcv_size;};
struct payload{mach_msg_header_t h;uint32_t sequence,value;unsigned char pad[20];};
struct receive{struct payload p;mach_msg_max_trailer_t trailer;};
typedef mach_msg_return_t(*msg2_t)(void*,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t);
static uint64_t pack(uint32_t low,uint32_t high){return low|((uint64_t)high<<32);}
int main(void){
 setbuf(stdout,NULL);unsigned checks=0;msg2_t msg2=dlsym(RTLD_DEFAULT,"mach_msg2_internal");CHECK(msg2);
 mach_port_t port=0;CHECK(mach_port_allocate(mach_task_self(),MACH_PORT_RIGHT_RECEIVE,&port)==0);CHECK(mach_port_insert_right(mach_task_self(),port,port,MACH_MSG_TYPE_MAKE_SEND)==0);
 struct payload* data=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANON,-1,0);CHECK(data!=MAP_FAILED);data->sequence=0x12345678;data->value=0xabcdef01;memset(data->pad,0x76,sizeof data->pad);CHECK(sizeof *data==52&&mprotect(data,4096,PROT_READ)==0);
 struct vector* outgoing=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANON,-1,0);CHECK(outgoing!=MAP_FAILED);outgoing[0]=(struct vector){.data=(uintptr_t)data,.send_size=sizeof *data};CHECK(mprotect(outgoing,4096,PROT_READ)==0);
 const uint32_t bits=MACH_MSGH_BITS(MACH_MSG_TYPE_COPY_SEND,0);
 for(unsigned round=0;round<16;round++){
  /* Exact observed layout: two send vectors,52-byte primary,empty auxiliary. */
  CHECK(msg2(outgoing,VECTOR|MQ|MACH_SEND_MSG|MACH_SEND_TIMEOUT|MACH_SEND_OVERRIDE,pack(bits,2),pack(port,0),pack(0,8000+round),0,0,1000)==0);
  struct receive unused={0},received={0};unsigned char aux[32];memset(aux,0xa5,sizeof aux);
  struct vector incoming[2]={{.data=(uintptr_t)&unused,.rcv=(uintptr_t)&received,.rcv_size=sizeof received},{.data=(uintptr_t)aux,.rcv_size=sizeof aux}};struct vector saved[2];memcpy(saved,incoming,sizeof saved);
  CHECK(msg2(incoming,VECTOR|MACH_RCV_MSG|MACH_RCV_TIMEOUT,0,0,0,pack(0,port),2,1000)==0);
  CHECK(received.p.h.msgh_id==(int)(8000+round)&&received.p.h.msgh_size==52&&received.p.sequence==data->sequence&&received.p.value==data->value&&!memcmp(received.p.pad,data->pad,sizeof data->pad));
  CHECK(!unused.p.h.msgh_id&&!memcmp(saved,incoming,sizeof saved));
  CHECK(!memcmp(aux,(unsigned char[8]){0},8));for(unsigned i=8;i<sizeof aux;i++)CHECK(aux[i]==0xa5);
 }
 CHECK(!data->h.msgh_bits&&!data->h.msgh_remote_port&&outgoing[0].send_size==52);
 CHECK(msg2(outgoing,VECTOR|MQ|MACH_SEND_MSG,pack(bits,3),pack(port,0),0,0,0,0)==MACH_SEND_INVALID_DATA);
 CHECK(msg2(outgoing,VECTOR|MQ|MACH_SEND_MSG,pack(bits,0),pack(port,0),0,0,0,0)==MACH_SEND_MSG_TOO_SMALL);
 CHECK(msg2((void*)1,VECTOR|MQ|MACH_SEND_MSG,pack(bits,1),pack(port,0),0,0,0,0)==MACH_SEND_INVALID_DATA);
 struct vector bad[2]={{.data=(uintptr_t)data,.send_size=sizeof *data},{.data=(uintptr_t)data,.send_size=1025}};
 CHECK(msg2(bad,VECTOR|MQ|MACH_SEND_MSG,pack(bits,2),pack(port,0),0,0,0,0)==0x10000019); /* auxiliary size exceeds XNU limit */
 bad[0].data=0;CHECK(msg2(bad,VECTOR|MQ|MACH_SEND_MSG,pack(bits,1),pack(port,0),0,0,0,0)==MACH_SEND_INVALID_DATA);bad[0].data=(uintptr_t)data;bad[0].send_size=25;
 CHECK(msg2(bad,VECTOR|MQ|MACH_SEND_MSG,pack(bits,1),pack(port,0),0,0,0,0)==MACH_SEND_MSG_TOO_SMALL);
 struct receive received={0};CHECK(mach_msg(&received.p.h,MACH_RCV_MSG|MACH_RCV_TIMEOUT,0,sizeof received,port,1,0)==MACH_RCV_TIMED_OUT); /* rejected sends consumed no queue slots */
 /* A receive-side validation failure must happen after a valid combined send. */
 CHECK(msg2(outgoing,VECTOR|MQ|MACH_SEND_MSG|MACH_RCV_MSG,pack(bits,1),pack(port,0),pack(0,9000),pack(0,port),0,0)==BAD_RECEIVE);
 struct vector incoming[2]={{.data=(uintptr_t)&received,.rcv_size=sizeof received},{0}};
 CHECK(msg2(incoming,VECTOR|MACH_RCV_MSG,0,0,0,pack(0,port),2,0)==BAD_RECEIVE);
 CHECK(msg2(incoming,VECTOR|MACH_RCV_MSG|MACH_RCV_TIMEOUT,0,0,0,pack(0,port),1,1000)==0&&received.p.h.msgh_id==9000);
 /* Complex header and descriptor count are captured separately from vector bytes. */
 struct{mach_msg_base_t base;mach_msg_port_descriptor_t d[2];} complex={0};complex.base.body.msgh_descriptor_count=99;
 for(unsigned i=0;i<2;i++)complex.d[i]=(mach_msg_port_descriptor_t){.name=port,.disposition=MACH_MSG_TYPE_COPY_SEND,.type=MACH_MSG_PORT_DESCRIPTOR};
 struct vector c={.data=(uintptr_t)&complex,.send_size=sizeof complex};CHECK(sizeof complex==52);
 CHECK(msg2(&c,VECTOR|MQ|MACH_SEND_MSG,pack(bits|MACH_MSGH_BITS_COMPLEX,1),pack(port,0),pack(0,9001),2,0,0)==0);
 struct{mach_msg_base_t base;mach_msg_port_descriptor_t d[2];mach_msg_max_trailer_t trailer;} cr={0};c=(struct vector){.data=(uintptr_t)&cr,.rcv_size=sizeof cr};
 CHECK(msg2(&c,VECTOR|MACH_RCV_MSG|MACH_RCV_TIMEOUT,0,0,0,pack(0,port),1,1000)==0&&cr.base.body.msgh_descriptor_count==2);
 for(unsigned i=0;i<2;i++){CHECK(cr.d[i].name==port);CHECK(mach_port_deallocate(mach_task_self(),cr.d[i].name)==0);}
 /* Valid one-vector kernel request plus two-vector reply, with separate buffers. */
 struct request{mach_msg_header_t h;NDR_record_t ndr;host_flavor_t flavor;mach_msg_type_number_t count;} req={.ndr=NDR_record,.flavor=HOST_BASIC_INFO,.count=HOST_BASIC_INFO_COUNT};
 struct reply{mach_msg_header_t h;NDR_record_t ndr;kern_return_t status;mach_msg_type_number_t count;integer_t info[68];mach_msg_max_trailer_t trailer;} rep={0};
 mach_port_t reply=0,host=mach_host_self();CHECK(mach_port_allocate(mach_task_self(),MACH_PORT_RIGHT_RECEIVE,&reply)==0);uint64_t aux=UINT64_MAX;
 struct vector both[2]={{.data=(uintptr_t)&req,.rcv=(uintptr_t)&rep,.send_size=sizeof req,.rcv_size=sizeof rep},{.data=(uintptr_t)&aux,.send_size=8,.rcv_size=8}};
 CHECK(msg2(both,VECTOR|KO|MACH_SEND_MSG|MACH_RCV_MSG|MACH_RCV_TIMEOUT,pack(MACH_MSGH_BITS(MACH_MSG_TYPE_COPY_SEND,MACH_MSG_TYPE_MAKE_SEND_ONCE),1),pack(host,reply),pack(0,200),pack(0,reply),2,1000)==0);
 CHECK(rep.h.msgh_id==300&&rep.status==0&&rep.count==HOST_BASIC_INFO_COUNT&&aux==0&&req.h.msgh_bits==0);
 CHECK(mach_port_destroy(mach_task_self(),reply)==0);CHECK(mach_port_deallocate(mach_task_self(),host)==0);CHECK(mach_port_destroy(mach_task_self(),port)==0);CHECK(munmap(data,4096)==0);CHECK(munmap(outgoing,4096)==0);
 printf("MSG2_VECTOR_REAL_CAPTURED_HEADERS_SEPARATE_BUFFERS_EMPTY_AUX_AND_ERRORS_OK checks=%u messages=19\n",checks);return 0;
}
