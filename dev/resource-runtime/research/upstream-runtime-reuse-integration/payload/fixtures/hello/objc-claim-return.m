#import <objc/NSObject.h>
#include <pthread/tsd_private.h>
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern id objc_claimAutoreleasedReturnValue(id) __attribute__((weak_import));
extern id objc_retainAutoreleasedReturnValue(id);
extern id objc_autoreleaseReturnValue(id);
extern void *objc_autoreleasePoolPush(void);
extern void objc_autoreleasePoolPop(void *);

#if !defined(__x86_64__)
#error This fixture validates the pinned Intel optimized-return ABI only.
#endif

static unsigned retains, releases, autoreleases, deallocs, checks;
#define CHECK(x) do { ++checks; if (!(x)) { \
    fprintf(stderr, "CLAIM_CHECK_FAILED %u %s\n", checks, #x); exit(20); \
} } while (0)

@interface ClaimObject : NSObject @end
@implementation ClaimObject
- (id)retain { ++retains; return [super retain]; }
- (oneway void)release { ++releases; [super release]; }
- (id)autorelease { ++autoreleases; return [super autorelease]; }
- (void)dealloc { ++deallocs; [super dealloc]; }
@end

static void reset_counts(void) {
    retains = releases = autoreleases = deallocs = 0;
}
static uintptr_t disposition(void) {
    return (uintptr_t)_pthread_getspecific_direct(__PTK_FRAMEWORK_OBJC_KEY4);
}
static void seed_disposition(uintptr_t value) {
    _pthread_setspecific_direct(__PTK_FRAMEWORK_OBJC_KEY4, (void *)value);
}

__attribute__((noinline)) static id old_producer_to_claim(id object) {
    id result = objc_autoreleaseReturnValue(object);
    result = objc_claimAutoreleasedReturnValue(result);
    asm volatile("" : "+r"(result));
    return result;
}
__attribute__((noinline)) static id old_optimized_pair(id object) {
    id result = objc_autoreleaseReturnValue(object);
    result = objc_retainAutoreleasedReturnValue(result);
    asm volatile("" : "+r"(result));
    return result;
}

int main(int argc, char **argv) {
    CHECK(argc == 3);
    setbuf(stdout, NULL);
    void *symbol = dlsym(RTLD_DEFAULT, "objc_claimAutoreleasedReturnValue");
    if (!strcmp(argv[2], "missing")) {
        CHECK(!symbol && !objc_claimAutoreleasedReturnValue);
        puts("OBJC_CLAIM_BASELINE_API_MISSING_OK");
        return 0;
    }
    CHECK(symbol && symbol == (void *)objc_claimAutoreleasedReturnValue);
    Dl_info owner;
    CHECK(dladdr(symbol, &owner) && strstr(owner.dli_fname, argv[1]));
    printf("OBJC_CLAIM_PROVIDER %s\n", owner.dli_fname);
    // Resolve both original stubs before the producer inspects their targets.
    CHECK(objc_retainAutoreleasedReturnValue(nil) == nil);
    CHECK(objc_claimAutoreleasedReturnValue(nil) == nil);
    CHECK(disposition() == 0);
    seed_disposition(1);
    CHECK(objc_claimAutoreleasedReturnValue(nil) == nil && disposition() == 0);

    void *pool = objc_autoreleasePoolPush();
    ClaimObject *object = [ClaimObject new];
    reset_counts();
    id result = objc_claimAutoreleasedReturnValue(object);
    CHECK(result == object && retains == 1 && disposition() == 0);
    [result release];
    CHECK(deallocs == 0);
    [object release];
    CHECK(deallocs == 1 && releases == 2 && autoreleases == 0);
    objc_autoreleasePoolPop(pool);
    puts("OBJC_CLAIM_FALLBACK_RETAIN_LIFETIME_OK");

    pool = objc_autoreleasePoolPush();
    object = [ClaimObject new];
    reset_counts();
    // Seed the actual upstream reserved TSD slot, without replacing any ARC
    // function. This isolates real +1 consumption and clearing in the new API.
    seed_disposition(1);
    result = objc_claimAutoreleasedReturnValue(object);
    CHECK(result == object && retains == 0 && disposition() == 0);
    result = objc_claimAutoreleasedReturnValue(result);
    CHECK(retains == 1 && disposition() == 0);
    [result release];
    CHECK(deallocs == 0);
    [object release];
    CHECK(deallocs == 1 && autoreleases == 0);
    objc_autoreleasePoolPop(pool);
    puts("OBJC_CLAIM_REAL_TSD_PLUS1_CONSUMED_ONCE_OK");

    pool = objc_autoreleasePoolPush();
    object = [ClaimObject new];
    reset_counts();
    result = old_optimized_pair(object);
    CHECK(result == object && retains == 0 && autoreleases == 0);
    CHECK(disposition() == 0);
    [result release];
    CHECK(deallocs == 1);
    objc_autoreleasePoolPop(pool);
    puts("OBJC_CLAIM_OLD_PRODUCER_OPTIMIZED_CONTROL_OK");

    pool = objc_autoreleasePoolPush();
    object = [ClaimObject new];
    reset_counts();
    result = old_producer_to_claim(object);
    CHECK(result == object && retains == 1 && autoreleases == 1);
    CHECK(disposition() == 0);
    [result release];
    CHECK(deallocs == 0);
    objc_autoreleasePoolPop(pool);
    CHECK(deallocs == 1);
    puts("OBJC_CLAIM_OLD_PRODUCER_UNRECOGNIZED_CALLSITE_CORRECT_FALLBACK_OK");
    printf("OBJC_CLAIM_RETURN_NATIVE_OK checks=%u\n", checks);
    return 0;
}
