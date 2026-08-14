qt_add_executable(helm-menu
    main.cpp
    launchermenu.cpp
)
target_link_libraries(helm-menu PRIVATE
    Qt6::Widgets
    helm-apps
    helm-wayland
    helm-appearance
    helm-common
)
install(TARGETS helm-menu RUNTIME DESTINATION ${CMAKE_INSTALL_PREFIX}/bin)
