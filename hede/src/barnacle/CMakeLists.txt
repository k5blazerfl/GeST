# Barnacle — the HeDE panel editor. barnacle-lib is the pure (Core-only,
# unit-tested) engine: the applet catalog + read/write of hede.conf [panel].
# The bar (helm-panel) reads it; the editor UI (a later slice) writes it.
qt_add_library(barnacle-lib STATIC
    catalog.cpp
    layout.cpp
)
target_include_directories(barnacle-lib PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(barnacle-lib PUBLIC Qt6::Core)
