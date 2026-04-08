cmake_minimum_required(VERSION 3.20)
project(VeloVersePhysics LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Platform-specific compile definitions
if(WIN32)
    add_compile_definitions(VELOVERSE_PLATFORM_WINDOWS)
elseif(APPLE)
    add_compile_definitions(VELOVERSE_PLATFORM_MACOS)
elseif(UNIX AND NOT APPLE)
    add_compile_definitions(VELOVERSE_PLATFORM_LINUX)
endif()

find_package(PkgConfig REQUIRED)
pkg_check_modules(DBUS REQUIRED dbus-1)
pkg_check_modules(GLIB REQUIRED glib-2.0)

option(BUILD_TESTING "Build tests" ON)

include(FetchContent)

FetchContent_Declare(
    nlohmann_json
    URL https://github.com/nlohmann/json/archive/refs/tags/v3.11.3.zip
)

FetchContent_MakeAvailable(nlohmann_json)

add_library(veloverse_physics
    Source/VeloVerse/Physics/ForceModel.cpp
    Source/VeloVerse/Physics/RouteProfile.cpp
    Source/VeloVerse/Physics/PhysicsEngine.cpp
    Source/VeloVerse/Physics/SimulatedTrainer.cpp
    Source/VeloVerse/Trainer/TrainerCalibration.cpp
    Source/VeloVerse/Trainer/TrainerManager.cpp
    Source/VeloVerse/Trainer/BLEFTMSDriver.cpp
    Source/VeloVerse/Trainer/ANTPlusFECDriver.cpp
    Source/VeloVerse/Trainer/CalibratedTrainer.cpp
    Source/VeloVerse/Sensors/BLEHRMDriver.cpp
)

target_include_directories(veloverse_physics
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/Source
        ${nlohmann_json_SOURCE_DIR}/include
)

target_link_libraries(veloverse_physics
    PUBLIC
)

add_executable(veloverse_app Source/main.cpp)
target_link_libraries(veloverse_app veloverse_physics)

if(BUILD_TESTING)
    FetchContent_Declare(
        googletest
        URL https://github.com/google/googletest/archive/refs/tags/v1.15.0.zip
    )
    set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
    FetchContent_MakeAvailable(googletest)

    enable_testing()

    add_executable(veloverse_physics_tests
        Source/VeloVerse/Physics/PhysicsTests.cpp
    )

    target_link_libraries(veloverse_physics_tests
        PRIVATE
            veloverse_physics
            GTest::gtest_main
    )

    include(GoogleTest)
    gtest_discover_tests(veloverse_physics_tests)
endif()


