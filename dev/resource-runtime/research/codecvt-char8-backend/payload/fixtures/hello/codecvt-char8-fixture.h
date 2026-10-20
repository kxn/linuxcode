#pragma once
#include <locale>
#include <typeinfo>
using Cv16 = std::codecvt<char16_t, char8_t, std::mbstate_t>;
using Cv32 = std::codecvt<char32_t, char8_t, std::mbstate_t>;
extern "C" const std::locale::id* char8_id16();
extern "C" const std::locale::id* char8_id32();
extern "C" const Cv16* char8_facet16(const std::locale*);
extern "C" const Cv32* char8_facet32(const std::locale*);
extern "C" const std::type_info* char8_type32(const std::locale*);
