cmake_minimum_required(VERSION 3.20)
project(VeloWorldPhysics LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

option(BUILD_TESTING "Build tests" ON)

include(FetchContent)

FetchContent_Declare(
    nlohmann_json
    URL https://github.com/nlohmann/json/archive/refs/tags/v3.11.3.zip
)

FetchContent_MakeAvailable(nlohmann_json)

add_library(veloworld_physics
    Source/VeloWorld/Physics/ForceModel.cpp
    Source/VeloWorld/Physics/RouteProfile.cpp
    Source/VeloWorld/Physics/PhysicsEngine.cpp
    Source/VeloWorld/Physics/SimulatedTrainer.cpp
    Source/VeloWorld/Trainer/TrainerCalibration.cpp
    Source/VeloWorld/Trainer/TrainerManager.cpp
)

target_include_directories(veloworld_physics
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/Source
        ${nlohmann_json_SOURCE_DIR}/include
)

if(BUILD_TESTING)
    FetchContent_Declare(
        googletest
        URL https://github.com/google/googletest/archive/refs/tags/v1.15.0.zip
    )
    set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
    FetchContent_MakeAvailable(googletest)

    enable_testing()

    add_executable(veloworld_physics_tests
        Source/VeloWorld/Physics/PhysicsTests.cpp
    )

    target_link_libraries(veloworld_physics_tests
        PRIVATE
            veloworld_physics
            GTest::gtest_main
    )

    include(GoogleTest)
    gtest_discover_tests(veloworld_physics_tests)
endif()


