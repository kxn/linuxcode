#include "codecvt-char8-fixture.h"
extern "C" const std::locale::id* char8_id16() { return &Cv16::id; }
extern "C" const std::locale::id* char8_id32() { return &Cv32::id; }
extern "C" const Cv16* char8_facet16(const std::locale* locale) {
    return &std::use_facet<Cv16>(*locale);
}
extern "C" const Cv32* char8_facet32(const std::locale* locale) {
    return &std::use_facet<Cv32>(*locale);
}
extern "C" const std::type_info* char8_type32(const std::locale* locale) {
    return &typeid(std::use_facet<Cv32>(*locale));
}
