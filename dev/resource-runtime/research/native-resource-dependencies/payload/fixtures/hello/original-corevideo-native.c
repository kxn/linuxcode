#include <CoreVideo/CoreVideo.h>
#include <CoreFoundation/CoreFoundation.h>
#include <assert.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct storage { unsigned releases; unsigned char bytes[7*64+32]; };
static void released(void *context, const void *address) {
    struct storage *storage=context;
    assert(address==storage->bytes+16);
    ++storage->releases;
}
int main(void) {
    setbuf(stdout,NULL);
    assert(!getenv("DISPLAY") && !getenv("WAYLAND_DISPLAY") && !getenv("XAUTHORITY"));
    Dl_info owner;
    assert(dladdr((void *)CVPixelBufferCreateWithBytes,&owner));
    assert(strstr(owner.dli_fname,"/coregraphics-native-") && strstr(owner.dli_fname,"/CoreVideo.framework/"));
    printf("ORIGINAL_COREVIDEO_IMPLEMENTATION_OWNER %s\n",owner.dli_fname);
    for (unsigned n=0;n<3;++n) {
        struct storage storage={0};
        memset(storage.bytes,0xa5,sizeof(storage.bytes));
        unsigned char *base=storage.bytes+16;
        for (unsigned row=0;row<7;++row) for (unsigned col=0;col<13;++col)
            for (unsigned component=0;component<4;++component)
                base[row*64+col*4+component]=(row*17+col*3+component+n)&255;
        unsigned char expected[sizeof(storage.bytes)];memcpy(expected,storage.bytes,sizeof(expected));
        CVPixelBufferRef buffer=NULL;
        assert(CVPixelBufferCreateWithBytes(kCFAllocatorDefault,13,7,kCVPixelFormatType_32BGRA,
            base,64,released,&storage,NULL,&buffer)==kCVReturnSuccess);
        assert(buffer && CFGetTypeID(buffer)==CVPixelBufferGetTypeID());
        assert(CVPixelBufferGetWidth(buffer)==13 && CVPixelBufferGetHeight(buffer)==7);
        assert(CVPixelBufferGetBytesPerRow(buffer)==64 && !CVPixelBufferIsPlanar(buffer));
        assert(CVPixelBufferGetPixelFormatType(buffer)==kCVPixelFormatType_32BGRA);
        assert(CVPixelBufferLockBaseAddress(buffer,kCVPixelBufferLock_ReadOnly)==kCVReturnSuccess);
        assert(CVPixelBufferGetBaseAddress(buffer)==base);
        assert(!memcmp(CVPixelBufferGetBaseAddress(buffer),expected+16,7*64));
        assert(CVPixelBufferUnlockBaseAddress(buffer,kCVPixelBufferLock_ReadOnly)==kCVReturnSuccess);
        CFStringRef value=CFStringCreateWithCString(NULL,"original-buffer-test",kCFStringEncodingUTF8);
        CVBufferSetAttachment(buffer,CFSTR("linuxcode-test"),value,kCVAttachmentMode_ShouldPropagate);
        CFRelease(value);
        CVAttachmentMode mode=kCVAttachmentMode_ShouldNotPropagate;
        CFTypeRef attachment=CVBufferGetAttachment(buffer,CFSTR("linuxcode-test"),&mode);
        assert(attachment && CFGetTypeID(attachment)==CFStringGetTypeID());
        assert(CFEqual(attachment,CFSTR("original-buffer-test")) && mode==kCVAttachmentMode_ShouldPropagate);
        CVBufferRemoveAttachment(buffer,CFSTR("linuxcode-test"));
        assert(!CVBufferGetAttachment(buffer,CFSTR("linuxcode-test"),NULL));
        CVPixelBufferRef retained=CVPixelBufferRetain(buffer);
        assert(retained==buffer);
        CVPixelBufferRelease(buffer);assert(storage.releases==0);
        CVPixelBufferRelease(retained);assert(storage.releases==1);
        assert(!memcmp(storage.bytes,expected,sizeof(expected)));
    }
    puts("ORIGINAL_COREVIDEO_CPU_PIXEL_BYTES_STRIDE_AND_OWNERSHIP_OK 3");
    puts("ORIGINAL_COREVIDEO_ATTACHMENT_TYPE_RETENTION_AND_REMOVAL_OK 3");
    return 0;
}
