cmake_minimum_required(VERSION 3.16)
project(ecosystem CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()
set(CMAKE_CXX_FLAGS_RELEASE "-O3")
add_compile_options(-Wall -Wextra)
add_link_options(-static)

add_library(core STATIC engine/world.cpp engine/io.cpp)
target_include_directories(core PUBLIC engine)

add_executable(eco_seq engine/main_seq.cpp)
target_link_libraries(eco_seq core)
