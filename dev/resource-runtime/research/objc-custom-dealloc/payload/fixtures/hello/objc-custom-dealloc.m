#import <objc/NSObject.h>
#include <objc/runtime.h>
#include <dlfcn.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern id objc_initWeak(id *, id);
extern id objc_initWeakOrNil(id *, id);
extern id objc_loadWeakRetained(id *);
extern void objc_destroyWeak(id *);
extern void *objc_autoreleasePoolPush(void);
extern void objc_autoreleasePoolPop(void *);

static unsigned initiated, destroyed, ordinary, checks;
static pthread_t initiation_thread;
static id pending;
static void (*mark_class)(Class);

#define CHECK(x) do { ++checks; if (!(x)) { \
    fprintf(stderr, "CUSTOM_DEALLOC_CHECK_FAILED %u %s\n", checks, #x); \
    exit(15); } } while (0)

@interface Deferred : NSObject { @public unsigned cookie; }
@end
@implementation Deferred
- (void)_objc_initiateDealloc {
    ++initiated;
    initiation_thread = pthread_self();
    pending = self;
}
- (void)dealloc {
    CHECK(cookie == 0xc0ffee);
    ++destroyed;
    [super dealloc];
}
@end
@interface AlreadyRealized : Deferred @end
@implementation AlreadyRealized @end
@interface LaterRealized : Deferred @end
@implementation LaterRealized @end
@interface Ordinary : NSObject @end
@implementation Ordinary
- (void)dealloc { ++ordinary; [super dealloc]; }
@end

static void *release_last(void *object) {
    [(id)object release];
    return NULL;
}

static void exercise(Class cls, int worker, int require_raw, int weak_fatal) {
    unsigned initial_i = initiated, initial_d = destroyed;
    Deferred *object = [cls new];
    object->cookie = 0xc0ffee;
    CHECK(((*(uintptr_t *)(void *)object & 1) == 0) == require_raw);
    id weak = nil;
    CHECK(objc_initWeak(&weak, object) == object);
    id retained = objc_loadWeakRetained(&weak);
    CHECK(retained == object);
    [retained release];
    pending = nil;
    if (worker) {
        pthread_t thread;
        CHECK(pthread_create(&thread, NULL, release_last, object) == 0);
        CHECK(pthread_join(thread, NULL) == 0);
        CHECK(!pthread_equal(initiation_thread, pthread_self()));
    } else {
        [object release];
        CHECK(pthread_equal(initiation_thread, pthread_self()));
    }
    CHECK(pending == object && initiated == initial_i + 1);
    CHECK(destroyed == initial_d);
    CHECK(objc_loadWeakRetained(&weak) == nil);
    CHECK(object->cookie == 0xc0ffee);
    id new_weak = nil;
    CHECK(objc_initWeakOrNil(&new_weak, object) == nil && new_weak == nil);
    objc_destroyWeak(&new_weak);
    if (weak_fatal) {
        fprintf(stderr, "CUSTOM_DEALLOC_WEAK_FATAL_EXPECTED\n");
        fflush(stderr);
        objc_initWeak(&new_weak, object);
        exit(16);
    }
    for (unsigned i = 0; i < 64; ++i) {
        [object retain];
        [object release];
        CHECK(initiated == initial_i + 1 && destroyed == initial_d);
        CHECK(objc_loadWeakRetained(&weak) == nil);
    }
    void *pool = objc_autoreleasePoolPush();
    [object autorelease];
    [object autorelease];
    [object dealloc];
    CHECK(destroyed == initial_d + 1);
    // Draining after actual destruction catches an incorrectly queued object.
    objc_autoreleasePoolPop(pool);
    CHECK(initiated == initial_i + 1 && destroyed == initial_d + 1);
    CHECK(weak == nil && objc_loadWeakRetained(&weak) == nil);
    objc_destroyWeak(&weak);
    pending = nil;
}

int main(int argc, char **argv) {
    if (argc != 4) return 10;
    mark_class = dlsym(RTLD_DEFAULT, "_class_setCustomDeallocInitiation");
    if (!mark_class) { puts("CUSTOM_DEALLOC_API_MISSING"); return 12; }
    Dl_info info;
    CHECK(dladdr((void *)mark_class, &info));
    CHECK(strstr(info.dli_fname, argv[1]) != NULL);
    printf("CUSTOM_DEALLOC_PROVIDER %s\n", info.dli_fname);
    int raw = atoi(argv[2]);
    void *outer = objc_autoreleasePoolPush();
    [[Ordinary new] release];
    CHECK(ordinary == 1);
    Deferred *unmarked = [Deferred new];
    unmarked->cookie = 0xc0ffee;
    [unmarked release];
    CHECK(initiated == 0 && destroyed == 1);
    Class before = [AlreadyRealized class];
    Class dynamic_before = objc_allocateClassPair(before, "DynamicBeforeMark", 0);
    CHECK(dynamic_before != Nil);
    objc_registerClassPair(dynamic_before);
    mark_class([Deferred class]);
    // Repeated marking is valid and must not affect existing object state.
    for (unsigned i = 0; i < 100; ++i) mark_class([Deferred class]);
    Class after = [LaterRealized class];
    Class dynamic_after = objc_allocateClassPair([Deferred class], "DynamicAfterMark", 0);
    CHECK(dynamic_after != Nil);
    objc_registerClassPair(dynamic_after);
    Class classes[] = { [Deferred class], before, after, dynamic_before, dynamic_after };
    for (unsigned c = 0; c < sizeof(classes) / sizeof(classes[0]); ++c)
        for (int worker = 0; worker < 2; ++worker)
            exercise(classes[c], worker, raw, !strcmp(argv[3], "weak-fatal"));
    CHECK(initiated == 10 && destroyed == 11);
    [[Ordinary new] release];
    CHECK(ordinary == 2);
    objc_autoreleasePoolPop(outer);
    if (!strcmp(argv[3], "wrong-count")) CHECK(destroyed == 12);
    printf("CUSTOM_DEALLOC_REAL_INHERITANCE_THREADS_WEAK_AUTORELEASE_OK %u raw=%d\n", checks, raw);
    return 0;
}
