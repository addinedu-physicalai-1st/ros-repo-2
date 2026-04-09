cmake_minimum_required(VERSION 3.8)
project(pinky_gz_sim)

if(POLICY CMP0068)
  cmake_policy(SET CMP0068 NEW)
endif()

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

if(APPLE)
  # Avoid install_name_tool -delete_rpath noise during install on macOS.
  set(CMAKE_SKIP_BUILD_RPATH TRUE CACHE BOOL "" FORCE)
  set(CMAKE_SKIP_INSTALL_RPATH TRUE CACHE BOOL "" FORCE)
  set(CMAKE_INSTALL_REMOVE_ENVIRONMENT_RPATH FALSE CACHE BOOL "" FORCE)
endif()

find_package(ament_cmake REQUIRED)
find_package(tinyxml2 REQUIRED CONFIG)

# Some Gazebo packages expect the upstream TinyXML2 target name, while the
# Conda package in this environment only exports tinyxml2::tinyxml2.
# INTERFACE IMPORTED is more portable across Ubuntu (RPi5) and macOS than ALIAS.
if(TARGET tinyxml2::tinyxml2 AND NOT TARGET TINYXML2::TINYXML2)
  add_library(TINYXML2::TINYXML2 INTERFACE IMPORTED)
  target_link_libraries(TINYXML2::TINYXML2 INTERFACE tinyxml2::tinyxml2)
endif()

find_package(ros_gz REQUIRED)
find_package(gz_ros2_control REQUIRED)

find_package(gz-sim8)
find_package(gz-plugin2)

include_directories(plugins)

# Optional plugin: absent on many ARM images without libgz-sim dev packages;
# worlds/models/launch still install for bringup without the plugin.
if(gz-sim8_FOUND AND gz-plugin2_FOUND)
  add_library(gz-sim-lamp-control-system
    SHARED
    plugins/gz_lamp_control_plugin.cpp
  )

  target_link_libraries(gz-sim-lamp-control-system PRIVATE gz-sim8::core gz-plugin2::register)

  ament_target_dependencies(gz-sim-lamp-control-system)

  install(
    TARGETS
    gz-sim-lamp-control-system
    DESTINATION
    lib
  )
endif()

install(
  DIRECTORY
    worlds
    models
    launch
    params
  DESTINATION share/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  set(ament_cmake_copyright_FOUND TRUE)
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
