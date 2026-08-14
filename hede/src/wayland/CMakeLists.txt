qt_add_library(helm-wayland STATIC
    layershell.cpp
)
target_include_directories(helm-wayland PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(helm-wayland PUBLIC Qt6::Gui LayerShellQt::Interface)
