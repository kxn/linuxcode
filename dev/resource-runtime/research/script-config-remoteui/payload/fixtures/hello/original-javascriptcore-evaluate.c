#include <JavaScriptCore/JavaScript.h>
#include <dlfcn.h>
#include <stdio.h>
#include <string.h>

int main(int argc, char **argv) {
    if (argc != 3) return 10;
    void *library = dlopen(argv[1], RTLD_NOW | RTLD_GLOBAL);
    if (!library) { fprintf(stderr,"JSC_LOAD_FAILED %s\n",dlerror()); return 11; }
#define LOAD(name) __typeof__(&name) f_##name = (__typeof__(&name))dlsym(library, #name); if (!f_##name) return 12
    LOAD(JSGlobalContextCreate); LOAD(JSGlobalContextRelease);
    LOAD(JSStringCreateWithUTF8CString); LOAD(JSStringRelease);
    LOAD(JSEvaluateScript); LOAD(JSValueToNumber); LOAD(JSValueToStringCopy);
    LOAD(JSStringGetUTF8CString); LOAD(JSValueIsNumber);
    Dl_info owner;
    if (!dladdr(f_JSGlobalContextCreate, &owner) || !owner.dli_fname || !strstr(owner.dli_fname, argv[2])) return 13;
    printf("JSC_ORIGINAL_PROVIDER %s\n", owner.dli_fname); fflush(stdout);
    JSGlobalContextRef context = f_JSGlobalContextCreate(NULL);
    if (!context) return 14;
    puts("JSC_REAL_CONTEXT_CREATED"); fflush(stdout);
    const char *scripts[] = {
        "21*2",
        "(()=>{let s=0; for(let i=0;i<10000;++i)s+=i; return s;})()",
        "(()=>{const a=new Uint32Array([3,5,8]); return a.reduce((s,x)=>s+x,0);})()",
        "JSON.parse('{\"a\":[4,9,16]}').a.map(x=>Math.sqrt(x)).join(',') === '2,3,4' ? 1 : 0",
        "Array.from('你好🌍').length",
        "(()=>{const f=x=>y=>x+y;return f(17)(25);})()",
        "var isolatedValue=123; isolatedValue"
    };
    const double expected[] = {42,49995000,16,1,3,42,123};
    for (unsigned i=0;i<sizeof(expected)/sizeof(expected[0]);++i) {
        JSStringRef script=f_JSStringCreateWithUTF8CString(scripts[i]);
        JSValueRef exception=NULL;
        JSValueRef value=f_JSEvaluateScript(context,script,NULL,NULL,1,&exception);
        f_JSStringRelease(script);
        if (!value || exception || !f_JSValueIsNumber(context,value)) return 20+i;
        double actual=f_JSValueToNumber(context,value,&exception);
        if (exception || actual!=expected[i]) return 30+i;
    }
    JSStringRef script=f_JSStringCreateWithUTF8CString("throw new Error('expected-test-exception')");
    JSValueRef exception=NULL;
    f_JSEvaluateScript(context,script,NULL,NULL,1,&exception); f_JSStringRelease(script);
    if (!exception) return 40;
    JSStringRef message=f_JSValueToStringCopy(context,exception,NULL); char text[256];
    if (!message || !f_JSStringGetUTF8CString(message,text,sizeof(text)) || !strstr(text,"expected-test-exception")) return 41;
    f_JSStringRelease(message);
    JSGlobalContextRef second=f_JSGlobalContextCreate(NULL); if (!second) return 42;
    script=f_JSStringCreateWithUTF8CString("typeof isolatedValue==='undefined' ? 1 : 0"); exception=NULL;
    JSValueRef value=f_JSEvaluateScript(second,script,NULL,NULL,1,&exception); f_JSStringRelease(script);
    if (!value || exception || f_JSValueToNumber(second,value,NULL)!=1) return 43;
    f_JSGlobalContextRelease(second); f_JSGlobalContextRelease(context);
    puts("ORIGINAL_JSC_EVALUATION_UNICODE_ARRAYS_EXCEPTIONS_AND_CONTEXT_ISOLATION_OK");
    return 0;
}
