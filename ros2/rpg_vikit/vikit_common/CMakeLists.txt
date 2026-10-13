cmake_minimum_required(VERSION 3.16)
project(vikit_common)
find_package(ament_cmake REQUIRED)
find_package(Eigen3 REQUIRED)
find_package(OpenCV REQUIRED)
find_package(Sophus REQUIRED)
find_package(fmt REQUIRED)
add_library(${PROJECT_NAME} SHARED
  src/atan_camera.cpp src/omni_camera.cpp src/math_utils.cpp src/vision.cpp
  src/performance_monitor.cpp src/robust_cost.cpp src/user_input_thread.cpp
  src/pinhole_camera.cpp src/equidistant_camera.cpp src/polynomial_camera.cpp
  src/homography.cpp src/img_align.cpp)
target_compile_features(${PROJECT_NAME} PUBLIC cxx_std_17)
target_include_directories(${PROJECT_NAME} PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
  ${OpenCV_INCLUDE_DIRS})
target_link_libraries(${PROJECT_NAME} PUBLIC Eigen3::Eigen Sophus::Sophus fmt::fmt ${OpenCV_LIBS})
install(DIRECTORY include/ DESTINATION include)
install(TARGETS ${PROJECT_NAME} EXPORT export_vikit_common
  ARCHIVE DESTINATION lib LIBRARY DESTINATION lib RUNTIME DESTINATION bin)
ament_export_targets(export_vikit_common HAS_LIBRARY_TARGET)
ament_export_include_directories(include)
ament_export_libraries(${PROJECT_NAME})
ament_export_dependencies(Eigen3 OpenCV Sophus fmt)
ament_package()
