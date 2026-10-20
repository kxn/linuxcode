#pragma once
#include <exception>

struct PrimaryError : std::exception {
    int code;
    explicit PrimaryError(int value);
    ~PrimaryError() noexcept override;
    const char* what() const noexcept override;
};

extern "C" void* primary_create_unowned(int code, void** header);
extern "C" void primary_destroy(void* object);
extern "C" unsigned primary_destroyed();
