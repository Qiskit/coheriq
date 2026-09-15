cmake_minimum_required(VERSION 3.15...4.0)
project(coheriq_ragged_engine LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Python 3.10 REQUIRED COMPONENTS Interpreter Development.Module)
find_package(nanobind CONFIG REQUIRED)

nanobind_add_module(_ragged_ext NB_STATIC src/ragged_ext.cpp)

install(TARGETS _ragged_ext LIBRARY DESTINATION coheriq_ragged_engine)
