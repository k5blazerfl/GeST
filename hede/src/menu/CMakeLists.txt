qt_add_library(helm-menu-lib STATIC
    launchermenu.cpp
    power.cpp
)
target_include_directories(helm-menu-lib PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(helm-menu-lib PUBLIC
    Qt6::Widgets
    Qt6::DBus
    helm-apps
    helm-appearance
    helm-common
)

qt_add_executable(helm-menu main.cpp)
target_link_libraries(helm-menu PRIVATE Qt6::Widgets helm-menu-lib helm-wayland)
install(TARGETS helm-menu RUNTIME DESTINATION ${CMAKE_INSTALL_PREFIX}/bin)
