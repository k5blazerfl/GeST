qt_add_library(helm-taskbar STATIC
    toplevelmodel.cpp
    foreigntoplevel.cpp
    identitymap.cpp
    taskbarwidget.cpp
)
target_include_directories(helm-taskbar PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(helm-taskbar PUBLIC
    Qt6::Widgets
    Qt6::WaylandClient
    helm-apps       # desktopentry: parse a window's synthesized .desktop for icon+name
)

# Generate the C++ client bindings + the C wl_interface tables for the wlr
# foreign-toplevel protocol. (The C file requires project LANGUAGES to include C.)
qt6_generate_wayland_protocol_client_sources(helm-taskbar
    FILES ${CMAKE_SOURCE_DIR}/protocols/wlr-foreign-toplevel-management-unstable-v1.xml
)
