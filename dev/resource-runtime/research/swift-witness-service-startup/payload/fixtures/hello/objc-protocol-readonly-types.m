#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#include <assert.h>
#include <dlfcn.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
@protocol LinuxcodeReadonlyTypes
@required
- (void)zRequired:(NSString *)s reply:(void (^)(NSString *))reply;
- (void)aRequired:(NSNumber *)n reply:(void (^)(NSNumber *))reply;
+ (void)zClass:(NSData *)d reply:(void (^)(NSData *))reply;
+ (void)aClass:(NSArray *)a reply:(void (^)(NSArray *))reply;
@optional
- (void)zOptional:(NSDictionary *)d reply:(void (^)(NSDictionary *))reply;
- (void)aOptional:(NSSet *)s reply:(void (^)(NSSet *))reply;
+ (void)zOptionalClass:(NSURL *)u reply:(void (^)(NSURL *))reply;
+ (void)aOptionalClass:(NSDate *)d reply:(void (^)(NSDate *))reply;
@end
/* Owned fixture: the pinned Intel protocol/method ABI, never Apple metadata. */
typedef struct {SEL name;const char *types;IMP implementation;} Entry;
typedef struct {uint32_t flags,count;Entry methods[];} List;
typedef struct {void *isa;const char *name;void *protocols;List *lists[4];void *properties;uint32_t size,flags;const char **extended;} Header;
_Static_assert(offsetof(Header,extended)==72,"Intel protocol ABI");
typedef struct {SEL name;const char *extended;unsigned group;} Expected;
int main(void) {
 @autoreleasepool {
  Protocol *protocol=@protocol(LinuxcodeReadonlyTypes);Header *header=(Header *)protocol;
  assert(header->size>=sizeof(*header) && header->extended);
  Expected expected[8];const char *types[8];unsigned total=0;
  for(unsigned group=0;group<4;++group){
   List *old=header->lists[group];assert(old && old->count==2 && (old->flags&0xfffffffcu)==sizeof(Entry));
   List *copy=malloc(8+2*sizeof(Entry));assert(copy);memcpy(copy,old,8+2*sizeof(Entry));copy->flags=sizeof(Entry);header->lists[group]=copy;
   for(unsigned i=0;i<2;++i){
    copy->methods[i].name=sel_registerName(sel_getName(copy->methods[i].name));
    types[total+i]=header->extended[total+i];assert(types[total+i]);
    expected[total+i]=(Expected){copy->methods[i].name,types[total+i],group};
   }
   if((uintptr_t)copy->methods[0].name<(uintptr_t)copy->methods[1].name){
    Entry temporary=copy->methods[0];copy->methods[0]=copy->methods[1];copy->methods[1]=temporary;
    const char *s=types[total];types[total]=types[total+1];types[total+1]=s;
   }
   total+=2;
  }
  size_t length=(size_t)getpagesize();void *page=mmap(NULL,length,PROT_READ|PROT_WRITE,MAP_ANON|MAP_PRIVATE,-1,0);assert(page!=MAP_FAILED);memcpy(page,types,sizeof(types));assert(!mprotect(page,length,PROT_READ));header->extended=page;header->flags&=~(3u<<30);
  puts("OBJC_PROTOCOL_READONLY_TYPES_PROTECTED groups=4 methods=8");fflush(stdout);
  const char *(*encoding)(Protocol *,SEL,BOOL,BOOL)=dlsym(RTLD_DEFAULT,"_protocol_getMethodTypeEncoding");assert(encoding);
  for(unsigned group=0;group<4;++group){
   unsigned count=0;struct objc_method_description *descriptions=protocol_copyMethodDescriptionList(protocol,group<2,group%2==0,&count);assert(descriptions && count==2);
   for(unsigned i=0;i<2;++i){
    Expected *found=NULL;for(unsigned j=0;j<8;++j)if(expected[j].group==group && expected[j].name==descriptions[i].name)found=&expected[j];assert(found);
    const char *actual=encoding(protocol,found->name,group<2,group%2==0);assert(actual && !strcmp(actual,found->extended));
   }
   free(descriptions);
  }
  assert(header->extended!=page && !memcmp(page,types,sizeof(types)));
  NSXPCInterface *interface=[NSXPCInterface interfaceWithProtocol:protocol];assert(interface && interface.protocol==protocol);
  for(unsigned group=0;group<4;++group){unsigned count=0;void *descriptions=protocol_copyMethodDescriptionList(protocol,group<2,group%2==0,&count);assert(count==2);free(descriptions);}
  assert(!memcmp(page,types,sizeof(types)));
  puts("OBJC_PROTOCOL_READONLY_TYPES_NATIVE_OK original_readonly_bytes_unchanged eight_extended_encodings_preserved four_method_groups repeat_queries original_NSXPCInterface");return 0;
 }
}
