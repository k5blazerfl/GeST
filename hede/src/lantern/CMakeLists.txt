# Lantern — the HeDE notification center (docs/design/lantern.md). lantern-lib is
# the pure display helpers + the D-Bus client of helm-notifyd's history API;
# helm-lantern is the right-edge layer-shell slide-out window.
qt_add_library(lantern-lib STATIC
    format.cpp
    client.cpp
    widgets.cpp
)
target_include_directories(lantern-lib PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(lantern-lib PUBLIC Qt6::Core Qt6::DBus helm-notify-lib)

qt_add_executable(helm-lantern
    main.cpp
    window.cpp
    sysinfowidget.cpp
)
target_link_libraries(helm-lantern PRIVATE
    Qt6::Widgets
    Qt6::DBus
    lantern-lib
    helm-wayland
    helm-appearance
    helm-common
)
install(TARGETS helm-lantern RUNTIME DESTINATION ${CMAKE_INSTALL_PREFIX}/bin)
