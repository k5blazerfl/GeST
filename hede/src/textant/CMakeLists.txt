# Textant — the HeDE terminal. libvterm owns the VT/xterm emulation; Qt Widgets
# own rendering, input, theming and integration. No KDE, no GTK. (P0 slice: a
# usable pty terminal; see docs/design/textant.md for the phasing.)

# libvterm (dev-libs/libvterm) — via pkg-config when it ships vterm.pc, else a
# plain header/library probe.
find_package(PkgConfig QUIET)
if(PkgConfig_FOUND)
    pkg_check_modules(VTERM IMPORTED_TARGET vterm)
endif()
if(NOT TARGET PkgConfig::VTERM)
    find_path(VTERM_INCLUDE_DIR NAMES vterm.h)
    find_library(VTERM_LIBRARY NAMES vterm)
    if(NOT VTERM_INCLUDE_DIR OR NOT VTERM_LIBRARY)
        message(FATAL_ERROR "Textant needs libvterm (dev-libs/libvterm): vterm.h / libvterm not found")
    endif()
    add_library(PkgConfig::VTERM UNKNOWN IMPORTED)
    set_target_properties(PkgConfig::VTERM PROPERTIES
        IMPORTED_LOCATION "${VTERM_LIBRARY}"
        INTERFACE_INCLUDE_DIRECTORIES "${VTERM_INCLUDE_DIR}")
endif()

qt_add_executable(textant
    main.cpp
    pty.cpp
    vtermsession.cpp
    terminalview.cpp)

target_link_libraries(textant PRIVATE
    Qt6::Widgets
    PkgConfig::VTERM
    util)              # forkpty() lives in libutil

install(TARGETS textant RUNTIME DESTINATION ${CMAKE_INSTALL_PREFIX}/bin)
