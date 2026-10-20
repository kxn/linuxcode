#include "codecvt-char8-fixture.h"
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <regex>
#include <sstream>
#include <thread>

static unsigned long long checks;
#define CHECK(value) do { ++checks; if (!(value)) { std::fprintf(stderr,"CHAR8_FAIL %d %s\n",__LINE__,#value); std::exit(1); } } while(0)

// Independent scalar encoding oracle. Facet code is not used to generate it.
static unsigned utf8(std::uint32_t cp, char8_t* out) {
    if (cp < 0x80) { out[0]=char8_t(cp); return 1; }
    if (cp < 0x800) { out[0]=char8_t(0xc0|(cp>>6)); out[1]=char8_t(0x80|(cp&63)); return 2; }
    if (cp < 0x10000) { out[0]=char8_t(0xe0|(cp>>12)); out[1]=char8_t(0x80|((cp>>6)&63)); out[2]=char8_t(0x80|(cp&63)); return 3; }
    out[0]=char8_t(0xf0|(cp>>18)); out[1]=char8_t(0x80|((cp>>12)&63)); out[2]=char8_t(0x80|((cp>>6)&63)); out[3]=char8_t(0x80|(cp&63)); return 4;
}

static unsigned destructions;
struct Custom32 : Cv32 { ~Custom32() override { ++destructions; } };

int main() {
    std::setbuf(stdout,nullptr);
    std::puts("CHAR8_NATIVE_TEST_BEGIN");
    CHECK(char8_id16()==&Cv16::id && char8_id32()==&Cv32::id);
    CHECK(static_cast<const void*>(&Cv16::id)!=static_cast<const void*>(&Cv32::id));
    CHECK(dlsym(RTLD_DEFAULT,"_ZNSt3__17codecvtIDiDu11__mbstate_tE2idE")==&Cv32::id);
    Dl_info owner;
    CHECK(dladdr(&Cv32::id,&owner) && owner.dli_fname);
    std::printf("CHAR8_CANONICAL_ID_OWNER %s\n",owner.dli_fname);
    std::locale locales[]={std::locale::classic(),std::locale("C"),std::locale()};
    for (const auto& locale : locales) {
        CHECK(std::has_facet<Cv16>(locale) && std::has_facet<Cv32>(locale));
        CHECK(char8_facet16(&locale)==&std::use_facet<Cv16>(locale));
        CHECK(char8_facet32(&locale)==&std::use_facet<Cv32>(locale));
        CHECK(char8_type32(&locale)==&typeid(std::use_facet<Cv32>(locale)));
    }
    const auto& c16=std::use_facet<Cv16>(locales[0]);
    const auto& c32=std::use_facet<Cv32>(locales[0]);
    CHECK(&typeid(c32)==&typeid(Cv32));
    CHECK(c16.encoding()==0 && c32.encoding()==0);
    CHECK(!c16.always_noconv() && !c32.always_noconv());
    CHECK(c16.max_length()==4 && c32.max_length()==4);
    for (const char8_t* literal : {u8"A",u8"\u00a2",u8"\u20ac",u8"\U0001f600",u8"\U0010ffff"}) {
        std::mbstate_t state{}; const char8_t* next; char32_t decoded[2],*end;
        auto size=std::char_traits<char8_t>::length(literal);
        CHECK(c32.in(state,literal,literal+size,next,decoded,decoded+2,end)==Cv32::ok);
        char8_t encoded[4]; CHECK(utf8(decoded[0],encoded)==size && !std::memcmp(encoded,literal,size));
    }
    unsigned scalars=0;
    for (std::uint32_t cp=0;cp<=0x10ffff;++cp) {
        if (cp>=0xd800 && cp<=0xdfff) continue;
        ++scalars;
        char8_t oracle[4],bytes[8]={}; unsigned n=utf8(cp,oracle);
        char32_t source=char32_t(cp),decoded[2]={},*decoded_next;
        const char32_t* from_next; char8_t* byte_next;
        const char8_t* byte_from_next;
        std::mbstate_t state{};
        CHECK(c32.out(state,&source,&source+1,from_next,bytes,bytes+8,byte_next)==Cv32::ok);
        CHECK(from_next==&source+1 && byte_next==bytes+n && !std::memcmp(bytes,oracle,n));
        CHECK(c32.in(state,oracle,oracle+n,byte_from_next,decoded,decoded+2,decoded_next)==Cv32::ok);
        CHECK(byte_from_next==oracle+n && decoded_next==decoded+1 && decoded[0]==source);
        CHECK(c32.length(state,oracle,oracle+n,1)==int(n));
        CHECK(c32.length(state,oracle,oracle+n,0)==0);
        char16_t utf16[2],output16[3]={},*out16_next;
        unsigned units=cp<0x10000?1:2;
        if (units==1) utf16[0]=char16_t(cp);
        else { utf16[0]=char16_t(0xd800+((cp-0x10000)>>10)); utf16[1]=char16_t(0xdc00+((cp-0x10000)&1023)); }
        const char16_t* from16_next;
        CHECK(c16.out(state,utf16,utf16+units,from16_next,bytes,bytes+8,byte_next)==Cv16::ok);
        CHECK(from16_next==utf16+units && byte_next==bytes+n && !std::memcmp(bytes,oracle,n));
        CHECK(c16.in(state,oracle,oracle+n,byte_from_next,output16,output16+3,out16_next)==Cv16::ok);
        CHECK(byte_from_next==oracle+n && out16_next==output16+units && !std::memcmp(utf16,output16,units*sizeof(char16_t)));
        CHECK(c16.length(state,oracle,oracle+n,units)==int(n));
        if (units==2) CHECK(c16.length(state,oracle,oracle+n,1)==0);
        // Representative boundary capacities and every incomplete UTF-8 prefix.
        if (cp<0x1000 || cp%1024==0 || cp==0x10ffff) {
            for (unsigned cap=0;cap<n;++cap) {
                std::memset(bytes,0x5a,sizeof(bytes));
                CHECK(c32.out(state,&source,&source+1,from_next,bytes,bytes+cap,byte_next)==Cv32::partial);
                CHECK(from_next==&source && byte_next==bytes && bytes[cap]==char8_t(0x5a));
                if (cap) {
                    CHECK(c32.in(state,oracle,oracle+cap,byte_from_next,decoded,decoded+2,decoded_next)==Cv32::partial);
                    CHECK(byte_from_next==oracle && decoded_next==decoded);
                }
            }
        }
    }
    const char8_t bad[][4]={{char8_t(0xc0),char8_t(0x80),0,0},{char8_t(0xe0),char8_t(0x80),char8_t(0x80),0},
        {char8_t(0xed),char8_t(0xa0),char8_t(0x80),0},{char8_t(0xf4),char8_t(0x90),char8_t(0x80),char8_t(0x80)},
        {char8_t(0xff),0,0,0},{char8_t(0xe2),char8_t(0x28),char8_t(0xa1),0}};
    const unsigned sizes[]={2,3,3,4,1,3};
    for (unsigned i=0;i<6;++i) {
        std::mbstate_t state{}; const char8_t* next; char32_t out32[4],*end32; char16_t out16[4],*end16;
        CHECK(c32.in(state,bad[i],bad[i]+sizes[i],next,out32,out32+4,end32)==Cv32::error);
        CHECK(next==bad[i] && end32==out32);
        CHECK(c16.in(state,bad[i],bad[i]+sizes[i],next,out16,out16+4,end16)==Cv16::error);
        CHECK(next==bad[i] && end16==out16);
    }
    for (char32_t cp : {char32_t(0xd800),char32_t(0xdfff),char32_t(0x110000),char32_t(0xffffffff)}) {
        std::mbstate_t state{}; const char32_t* next; char8_t bytes[8],*end;
        CHECK(c32.out(state,&cp,&cp+1,next,bytes,bytes+8,end)==Cv32::error);
        CHECK(next==&cp && end==bytes);
    }
    std::mbstate_t state{}; char8_t buffer[4],*end;
    CHECK(c32.unshift(state,buffer,buffer+4,end)==Cv32::noconv && end==buffer);
    CHECK(c16.unshift(state,buffer,buffer+4,end)==Cv16::noconv && end==buffer);
    { auto* custom=new Custom32; std::locale local(locales[0],custom); CHECK(&std::use_facet<Cv32>(local)==custom); CHECK(destructions==0); }
    CHECK(destructions==1);
    auto old_global=std::locale::global(locales[1]);
    CHECK(std::has_facet<Cv16>(std::locale()) && std::has_facet<Cv32>(std::locale()));
    std::locale::global(old_global);
    std::atomic<unsigned> errors{0}; std::thread threads[4];
    for (auto& thread : threads) thread=std::thread([&] {
        for (unsigned n=0;n<1000;++n) {
            std::locale local("C");
            if (char8_facet32(&local)!=&std::use_facet<Cv32>(local) || char8_id32()!=&Cv32::id) ++errors;
        }
    });
    for (auto& thread : threads) thread.join();
    CHECK(errors==0);
    std::ostringstream stream; stream.imbue(locales[0]); stream<<std::hex<<std::showbase<<255;
    CHECK(stream.str()=="0xff");
    std::istringstream input("123 1.25"); int integer=0;double real=0;input>>integer>>real;
    CHECK(integer==123 && real==1.25 && !input.fail());
    CHECK(std::regex_match("facet-2020",std::regex("[a-z]+-[0-9]+")));
    CHECK(scalars==1112064);
    std::printf("CHAR8_CLASSIC_NAMED_GLOBAL_CROSS_DSO_ALL_UNICODE_SCALARS_ERRORS_PARTIAL_LIFETIME_THREADS_AND_STREAMS_OK checks=%llu scalars=%u thread_queries=4000\n",checks,scalars);
}
