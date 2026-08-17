qt_add_library(helm-quicksettings STATIC
    proc.cpp
    volume.cpp
    brightness.cpp
    dndtoggle.cpp
)
target_include_directories(helm-quicksettings PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(helm-quicksettings PUBLIC Qt6::Widgets Qt6::DBus helm-appearance)
