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

add_library(core STATIC engine/world.cpp engine/io.cpp engine/cli.cpp)
target_include_directories(core PUBLIC engine)

add_executable(eco_seq engine/main_seq.cpp engine/sim_seq.cpp)
target_link_libraries(eco_seq core)

set(THREADS_PREFER_PTHREAD_FLAG ON)
find_package(Threads REQUIRED)
add_executable(eco_pth engine/main_pth.cpp engine/sim_pth.cpp)
target_link_libraries(eco_pth core Threads::Threads)

add_executable(rules_test tests/rules_test.cpp)
target_link_libraries(rules_test core)
