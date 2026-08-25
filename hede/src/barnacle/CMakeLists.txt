# Barnacle — the HeDE panel editor. barnacle-lib is the pure (Core-only,
# unit-tested) engine: the applet catalog, read/write of hede.conf [panel], and
# the editor's working model. The bar (helm-panel) reads it; the helm-barnacle
# window writes it, and the bar live-reloads.
qt_add_library(barnacle-lib STATIC
    catalog.cpp
    layout.cpp
    editor.cpp
)
target_include_directories(barnacle-lib PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(barnacle-lib PUBLIC Qt6::Core)

qt_add_executable(helm-barnacle
    main.cpp
    window.cpp
)
target_link_libraries(helm-barnacle PRIVATE
    Qt6::Widgets
    barnacle-lib
    helm-appearance
    helm-common
)
install(TARGETS helm-barnacle RUNTIME DESTINATION ${CMAKE_INSTALL_PREFIX}/bin)
