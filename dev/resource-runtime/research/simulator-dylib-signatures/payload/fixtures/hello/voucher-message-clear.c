#include <mach/mach.h>
#include <stdio.h>
#include <string.h>
#define CHECK(x) do { if(!(x)){printf("failed line %d: %s\n",__LINE__,#x);return 1;} } while(0)
static mach_msg_header_t message(mach_port_t port,mach_msg_type_name_t kind) {
    mach_msg_header_t h={0};h.msgh_bits=MACH_MSGH_BITS_COMPLEX|MACH_MSGH_BITS_SET(MACH_MSG_TYPE_MOVE_SEND,MACH_MSG_TYPE_COPY_SEND,kind,0);h.msgh_size=sizeof(h);h.msgh_id=123;h.msgh_voucher_port=port;return h;
}
static mach_port_urefs_t refs(mach_port_t port) {
    mach_port_urefs_t n=999;return mach_port_get_refs(mach_task_self(),port,MACH_PORT_RIGHT_SEND,&n)==KERN_SUCCESS?n:999;
}
int main(void) {
    mach_port_t port=0;CHECK(mach_port_allocate(mach_task_self(),MACH_PORT_RIGHT_RECEIVE,&port)==KERN_SUCCESS);
    CHECK(mach_port_insert_right(mach_task_self(),port,port,MACH_MSG_TYPE_MAKE_SEND)==KERN_SUCCESS);
    CHECK(mach_port_mod_refs(mach_task_self(),port,MACH_PORT_RIGHT_SEND,1)==KERN_SUCCESS);CHECK(refs(port)==2);
    mach_msg_header_t h=message(port,MACH_MSG_TYPE_COPY_SEND),expected=h;expected.msgh_bits&=~MACH_MSGH_BITS_VOUCHER_MASK;expected.msgh_voucher_port=0;
    voucher_mach_msg_clear(&h);CHECK(!memcmp(&h,&expected,sizeof(h)));CHECK(refs(port)==2);
    voucher_mach_msg_clear(&h);CHECK(refs(port)==2);
    h=message(port,MACH_MSG_TYPE_MOVE_SEND);voucher_mach_msg_clear(&h);CHECK(!memcmp(&h,&expected,sizeof(h)));CHECK(refs(port)==1);
    h=message(port,MACH_MSG_TYPE_MOVE_SEND_ONCE);expected=h;voucher_mach_msg_clear(&h);CHECK(!memcmp(&h,&expected,sizeof(h)));CHECK(refs(port)==1);
    h=message(0,MACH_MSG_TYPE_COPY_SEND);expected=h;voucher_mach_msg_clear(&h);CHECK(!memcmp(&h,&expected,sizeof(h)));
    CHECK(mach_port_destroy(mach_task_self(),port)==KERN_SUCCESS);
    puts("VOUCHER_MESSAGE_CLEAR_REAL_SEND_RIGHT_OWNERSHIP_NATIVE_OK");return 0;
}
