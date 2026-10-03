# A small library for scripts/ios-module-probe.py: no game code.
cmake_minimum_required(VERSION 3.20)
project(padmint_module_probe CXX)
set(CMAKE_CXX_STANDARD 20)
add_library(game SHARED probe.cpp)
# Names the app exports are found when the app loads the module (flat namespace).
target_link_options(game PRIVATE -Wl,-undefined,dynamic_lookup)
