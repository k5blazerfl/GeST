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
# backend write side (system bus). main.cpp only drives Hostname + System, but we
# generate and compile *every* interface XML so a broken template (a bad type, a
# missing QtTypeName annotation on a container out-arg) fails the build even before
# a view wires it up — this is what the cpp-reference CI job guards.
set(DBUS_SRCS)
qt_add_dbus_interface(DBUS_SRCS
    ${CMAKE_CURRENT_SOURCE_DIR}/interfaces/org.gentoo.gest.core1.Hostname.xml
    hostname_interface)
qt_add_dbus_interface(DBUS_SRCS
    ${CMAKE_CURRENT_SOURCE_DIR}/interfaces/org.gentoo.gest.System.xml
    system_interface)
qt_add_dbus_interface(DBUS_SRCS
    ${CMAKE_CURRENT_SOURCE_DIR}/interfaces/org.gentoo.gest.core1.Software.xml
    software_interface)
qt_add_dbus_interface(DBUS_SRCS
    ${CMAKE_CURRENT_SOURCE_DIR}/interfaces/org.gentoo.gest.core1.Catalog.xml
    catalog_interface)

# More of the WRITE side (system bus, polkit) beyond SetHostname: a second write
# interface (Services) and a container-typed write (Sysctl's a(ss)). The Sysctl
# proxy references the registered SysctlSettings type, so its generated header must
# #include our sysctl_types.h — that is what the source-file INCLUDE property does.
qt_add_dbus_interface(DBUS_SRCS
    ${CMAKE_CURRENT_SOURCE_DIR}/interfaces/org.gentoo.gest.Services.xml
    services_write_interface)
set_source_files_properties(
    ${CMAKE_CURRENT_SOURCE_DIR}/interfaces/org.gentoo.gest.Sysctl.xml
    PROPERTIES INCLUDE "${CMAKE_CURRENT_SOURCE_DIR}/sysctl_types.h")
qt_add_dbus_interface(DBUS_SRCS
    ${CMAKE_CURRENT_SOURCE_DIR}/interfaces/org.gentoo.gest.Sysctl.xml
    sysctl_write_interface)

add_executable(gest-hede-ref main.cpp ${DBUS_SRCS})
# the generated hostname_interface.h lands in the build dir
target_include_directories(gest-hede-ref PRIVATE ${CMAKE_CURRENT_BINARY_DIR})
target_link_libraries(gest-hede-ref PRIVATE Qt6::Core Qt6::DBus Qt6::Widgets)
