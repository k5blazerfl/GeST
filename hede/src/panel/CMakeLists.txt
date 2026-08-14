qt_add_executable(helm-panel
    main.cpp
    panel.cpp
    clock.cpp
    launcherbutton.cpp
)
target_link_libraries(helm-panel PRIVATE
    Qt6::Widgets
    helm-wayland
    helm-taskbar
    helm-common
)
install(TARGETS helm-panel RUNTIME DESTINATION ${CMAKE_INSTALL_PREFIX}/bin)
