// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
// Key function from libcxx/src/memory_resource.cpp at
// 2078da43e25a4623cab2d0d60decddf709aaea28. The SDK supplies the class ABI.
#include <memory_resource>

_LIBCPP_BEGIN_NAMESPACE_STD
namespace pmr {
memory_resource::~memory_resource() = default;
}
_LIBCPP_END_NAMESPACE_STD
