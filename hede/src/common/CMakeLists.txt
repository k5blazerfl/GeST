qt_add_library(helm-common STATIC
    config.cpp
    timefmt.cpp
)
target_include_directories(helm-common PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(helm-common PUBLIC Qt6::Core)
