# SeFE — the Seahorse File Explorer. sefe-lib holds the pure (Core-only,
# unit-tested) helpers; the sefe executable is the themed Qt Widgets window.
qt_add_library(sefe-lib STATIC sefe.cpp ops.cpp)
target_include_directories(sefe-lib PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(sefe-lib PUBLIC Qt6::Core hold-core) # hold-core: ArchiveModel + listing (browse-in-place)

qt_add_executable(sefe main.cpp window.cpp addressbar.cpp iconprovider.cpp throbber.cpp titlebar.cpp)
# The throbber — a 30-frame pixel-art sprite sheet (6×5): a Helm wheel under a
# cycling moon over a twinkling starfield. Embedded at :/seahorse/throbber.png.
qt_add_resources(sefe "seahorse_art"
    PREFIX "/seahorse"
    FILES throbber.png)
target_link_libraries(sefe PRIVATE
    Qt6::Widgets
    sefe-lib
    helm-appearance
    helm-apps    # desktopentry: scan + Exec argv for "Open with"
    helm-common
    hold-core    # archive engine: Extract / Compress (Hold H2)
)
install(TARGETS sefe RUNTIME DESTINATION ${CMAKE_INSTALL_PREFIX}/bin)
