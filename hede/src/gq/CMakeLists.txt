# General Quarters — the Ctrl+Alt+Del interrupt surface
# (docs/design/hede-session-supervision.md).
qt_add_executable(helm-gq
    main.cpp
    gqwindow.cpp
)
target_link_libraries(helm-gq PRIVATE
    Qt6::Widgets
    Qt6::DBus
    helm-appearance
    helm-common
    helm-wayland
)
install(TARGETS helm-gq RUNTIME DESTINATION ${CMAKE_INSTALL_PREFIX}/bin)
