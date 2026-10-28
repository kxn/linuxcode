#import <Foundation/Foundation.h>
#import <CoreServices/CoreServices.h>
#include <dlfcn.h>
#include <sys/stat.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
static const char *description(id value) {
    return value ? [[value description] UTF8String] : "<nil>";
}
static void owner(const char *name, const void *address) {
    Dl_info info={0};
    printf("WORKSPACE_UTI_OWNER %s %s\n",name,dladdr(address,&info)&&info.dli_fname?info.dli_fname:"<unknown>");
}
static int workspace_types(const char *path) {
    owner("UTTypeConformsTo",(const void *)UTTypeConformsTo);
    owner("UTTypeCreatePreferredIdentifierForTag",(const void *)UTTypeCreatePreferredIdentifierForTag);
    owner("CFURLCopyResourcePropertyForKey",(const void *)CFURLCopyResourcePropertyForKey);
    NSString *string=[NSString stringWithUTF8String:path];
    NSURL *url=[NSURL fileURLWithPath:string isDirectory:YES];
    struct stat buffer={0};int found=stat(path,&buffer);int failure=errno;
    printf("WORKSPACE_UTI_STAT status=%d errno=%d directory=%d mode=%o\n",found,found?failure:0,!found&&S_ISDIR(buffer.st_mode),(unsigned)(buffer.st_mode&0777));
    NSError *error=nil;NSData *contents=[NSData dataWithContentsOfFile:[string stringByAppendingPathComponent:@"contents.xcworkspacedata"] options:0 error:&error];
    printf("WORKSPACE_UTI_CONTENTS bytes=%lu error=%s\n",(unsigned long)[contents length],description(error));
    for(NSString *key in @[NSURLIsDirectoryKey,NSURLTypeIdentifierKey,NSURLContentTypeKey]) {
        id value=nil;error=nil;BOOL ok=[url getResourceValue:&value forKey:key error:&error];
        printf("WORKSPACE_UTI_RESOURCE key=%s ok=%d value=%s error=%s\n",[key UTF8String],ok,description(value),description(error));
    }
    Boolean xml=UTTypeConformsTo(CFSTR("com.apple.xml-property-list"),CFSTR("com.apple.property-list"));
    Boolean workspace=UTTypeConformsTo(CFSTR("com.apple.dt.document.workspace"),CFSTR("com.apple.package"));
    printf("WORKSPACE_UTI_CONFORMS xml-property-list_to_property-list=%d workspace_to_package=%d\n",xml,workspace);
    CFStringRef preferred=UTTypeCreatePreferredIdentifierForTag(kUTTagClassFilenameExtension,CFSTR("xcworkspace"),NULL);
    printf("WORKSPACE_UTI_PREFERRED xcworkspace=%s\n",description((id)preferred));
    for(NSString *identifier in @[@"com.apple.xml-property-list",@"com.apple.property-list",@"com.apple.dt.document.workspace"]) {
        CFDictionaryRef declaration=UTTypeCopyDeclaration((CFStringRef)identifier);
        printf("WORKSPACE_UTI_DECLARATION identifier=%s present=%d conforms=%s\n",[identifier UTF8String],declaration!=NULL,description([(NSDictionary *)declaration objectForKey:@"UTTypeConformsTo"]));
        if(declaration)CFRelease(declaration);
    }
    if(preferred)CFRelease(preferred);
    puts("WORKSPACE_UTI_DIAGNOSTIC_COMPLETE (completion is not a conformance pass)");
    return 0;
}
static int register_workspace_types(const char *path) {
    puts("WORKSPACE_UTI_BEFORE_REGISTRATION");workspace_types(path);
    owner("LSRegisterURL",(const void *)LSRegisterURL);
    for(NSString *bundle in @[@"/System/Library/CoreServices/CoreTypes.bundle",@"/Applications/Xcode.app"]) {
        NSURL *url=[NSURL fileURLWithPath:bundle isDirectory:YES];
        OSStatus status=LSRegisterURL((CFURLRef)url,true);
        printf("WORKSPACE_UTI_REGISTER path=%s status=%d\n",[bundle UTF8String],(int)status);
    }
    puts("WORKSPACE_UTI_AFTER_REGISTRATION");return workspace_types(path);
}
int main(int argc,char **argv) {
    setbuf(stdout,NULL);
    @autoreleasepool {
        if(argc==3&&!strcmp(argv[1],"--uti-workspace"))return workspace_types(argv[2]);
        if(argc==3&&!strcmp(argv[1],"--uti-workspace-register"))return register_workspace_types(argv[2]);
        if(argc>1 && !strcmp(argv[1],"--wait")) {
            printf("CORETYPES_METADATA_READY %d\n",getpid());
            FILE *gate=fopen("/Volumes/SystemRoot/workspace/runtime/coretypes-debug-release","r");
            if(!gate)return 2;fgetc(gate);fclose(gate);
        }
        NSString *path=@"/System/Library/CoreServices/CoreTypes.bundle";
        NSURL *url=[NSURL fileURLWithPath:path isDirectory:YES];
        NSError *error=nil; id value=nil;
        BOOL ok=[url getResourceValue:&value forKey:NSURLIsDirectoryKey error:&error];
        printf("CORETYPES_URL_IS_DIRECTORY ok=%d value=%s error=%s\n",ok,[[value description] UTF8String],[[error description] UTF8String]);
        error=nil;NSDictionary *attrs=[[NSFileManager defaultManager] attributesOfItemAtPath:path error:&error];
        printf("CORETYPES_FILEMANAGER_ATTRIBUTES count=%lu error=%s\n",(unsigned long)[attrs count],[[error description] UTF8String]);
        __block BOOL enumerationError=NO;
        NSDirectoryEnumerator *enumerator=[[NSFileManager defaultManager] enumeratorAtURL:url includingPropertiesForKeys:@[NSURLNameKey,NSURLIsDirectoryKey,NSURLIsRegularFileKey,NSURLFileSizeKey] options:0 errorHandler:^BOOL(NSURL *entry,NSError *failure) {
            enumerationError=YES;printf("CORETYPES_ENUMERATION_ERROR %s\n",[[failure description] UTF8String]);return NO;
        }];
        printf("CORETYPES_ENUMERATOR_CLASS %s\n",[NSStringFromClass([enumerator class]) UTF8String]);
        unsigned count=0;for(NSURL *entry in enumerator) {printf("CORETYPES_ENUMERATED %s\n",[[entry path] UTF8String]);if(++count==3)break;}
        if(!count) {
            NSURL *next=[enumerator nextObject];
            printf("CORETYPES_ENUMERATOR_NEXT %s\n",[[next path] UTF8String]);
            NSError *listingError=nil;
            NSArray *listing=[[NSFileManager defaultManager] contentsOfDirectoryAtPath:path error:&listingError];
            printf("CORETYPES_DIRECTORY_LISTING count=%lu error=%s\n",(unsigned long)[listing count],[[listingError description] UTF8String]);
        }
        printf("CORETYPES_METADATA_RESULT directory=%d attributes=%d enumeration=%u errors=%d\n",ok&&[value boolValue],attrs!=nil,count,enumerationError);
        return !(ok&&[value boolValue]&&attrs&&count&&!enumerationError);
    }
}
