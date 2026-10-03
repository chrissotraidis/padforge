# A small library for scripts/ios-module-probe.py: no game code.
cmake_minimum_required(VERSION 3.20)
project(padmint_module_probe C CXX)
set(CMAKE_CXX_STANDARD 20)
add_library(game SHARED probe.cpp probe_c.c)
# Like a game's own CMake project: no PadMint-specific link options, and -lm as with Xcode.
target_link_libraries(game PRIVATE m)
