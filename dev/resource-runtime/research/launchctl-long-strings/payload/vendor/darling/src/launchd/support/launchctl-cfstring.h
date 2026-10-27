/* Preserve full UTF-8 plist strings when preparing launchd arguments and env. */
#ifndef DARLING_LAUNCHCTL_CFSTRING_H
#define DARLING_LAUNCHCTL_CFSTRING_H
#include <CoreFoundation/CoreFoundation.h>
#include <limits.h>
#include <stdlib.h>
#include <string.h>
static char *launchctl_copy_cfstring(CFStringRef value) {
    CFIndex length=CFStringGetLength(value);
    CFIndex maximum=CFStringGetMaximumSizeForEncoding(length,kCFStringEncodingUTF8);
    if(maximum<0||maximum==LONG_MAX)return NULL;
    char *buffer=malloc((size_t)maximum+1);if(!buffer)return NULL;
    CFIndex used=0;
    CFIndex converted=CFStringGetBytes(value,CFRangeMake(0,length),kCFStringEncodingUTF8,
                                     0,false,(UInt8*)buffer,maximum,&used);
    if(converted!=length||memchr(buffer,0,(size_t)used)){free(buffer);return NULL;}
    buffer[used]=0;return buffer;
}
#endif
