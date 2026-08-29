# EzRA — the HeDE task manager. ezra-lib is the pure (Core-only, unit-tested)
# engine: /proc parsers, the delta samplers, and the Processes table model.
# The ezra window sits on top (Barnacle pattern).
qt_add_library(ezra-lib STATIC
    sampler.cpp
    processmodel.cpp
    usermodel.cpp
    services.cpp
    sensors.cpp
    startupmodel.cpp
)
target_include_directories(ezra-lib PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
# DBus: the Services engine talks to systemd's Manager on the system bus.
# helm-apps: the Startup tab shares the XDG autostart engine with the
# session's helm-autostart runner.
target_link_libraries(ezra-lib PUBLIC Qt6::Core Qt6::DBus helm-apps)

qt_add_executable(ezra
    main.cpp
    window.cpp
    graph.cpp
)
target_link_libraries(ezra PRIVATE
    Qt6::Widgets
    ezra-lib
    helm-appearance
    helm-common
)
install(TARGETS ezra RUNTIME DESTINATION ${CMAKE_INSTALL_PREFIX}/bin)
