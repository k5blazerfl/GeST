qt_add_library(helm-media STATIC
    mpris.cpp
)
target_include_directories(helm-media PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(helm-media PUBLIC Qt6::Widgets Qt6::DBus)
