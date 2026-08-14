# A minimal Qt6 reference client for gestd — the HeDE-side template.
#
# `qt_add_dbus_interface` is CMake's wrapper around `qdbusxml2cpp`: it takes the
# gestd interface XML (captured from `busctl`/`gdbus introspect`) and generates a
# typed C++ proxy class the view calls like any local object. This is exactly how
# HeDE's C++/Qt Control Center consumes gestd — no Portage, no Python in-process.
#
#   cmake -S . -B build && cmake --build build
#   gest-core &                       # start gestd on the session bus
#   ./build/gest-hede-ref             # the GUI (needs a display)
#   ./build/gest-hede-ref --once      # headless: fetch, print, exit (QT_QPA_PLATFORM=offscreen)
cmake_minimum_required(VERSION 3.16)
project(gest_hede_ref LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)

find_package(Qt6 REQUIRED COMPONENTS Core DBus Widgets)

# Generate typed proxies: the gestd read side (session bus) and the polkit root
# backend write side (system bus).
set(DBUS_SRCS)
qt_add_dbus_interface(DBUS_SRCS
    ${CMAKE_CURRENT_SOURCE_DIR}/interfaces/org.gentoo.gest.core1.Hostname.xml
    hostname_interface)
qt_add_dbus_interface(DBUS_SRCS
    ${CMAKE_CURRENT_SOURCE_DIR}/interfaces/org.gentoo.gest.System.xml
    system_interface)

add_executable(gest-hede-ref main.cpp ${DBUS_SRCS})
# the generated hostname_interface.h lands in the build dir
target_include_directories(gest-hede-ref PRIVATE ${CMAKE_CURRENT_BINARY_DIR})
target_link_libraries(gest-hede-ref PRIVATE Qt6::Core Qt6::DBus Qt6::Widgets)
