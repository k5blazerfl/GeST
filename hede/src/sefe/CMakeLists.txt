# SeFE — the Seahorse File Explorer. sefe-lib holds the pure (Core-only,
# unit-tested) helpers; the sefe executable is the themed Qt Widgets window.
qt_add_library(sefe-lib STATIC sefe.cpp ops.cpp archivemodel.cpp)
target_include_directories(sefe-lib PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(sefe-lib PUBLIC Qt6::Core hold-core) # hold-core: archive listing (browse-in-place)

qt_add_executable(sefe main.cpp window.cpp addressbar.cpp iconprovider.cpp throbber.cpp)
# The throbber scene — a ship's wheel over a planet in a teal starfield (the
# static base; the widget animates falling stars over it). Embedded at
# :/seahorse/base.png.
qt_add_resources(sefe "seahorse_art"
    PREFIX "/seahorse"
    FILES base.png)
target_link_libraries(sefe PRIVATE
    Qt6::Widgets
    sefe-lib
    helm-appearance
    helm-apps    # desktopentry: scan + Exec argv for "Open with"
    helm-common
    hold-core    # archive engine: Extract / Compress (Hold H2)
)
install(TARGETS sefe RUNTIME DESTINATION ${CMAKE_INSTALL_PREFIX}/bin)
