cmake_minimum_required(VERSION 3.21)
project(hede VERSION 0.0.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

find_package(Qt6 REQUIRED COMPONENTS Widgets Test WaylandClient DBus)
find_package(LayerShellQt REQUIRED)

qt_standard_project_setup()
enable_testing()

add_subdirectory(src/common)
add_subdirectory(src/apps)
add_subdirectory(src/wayland)
add_subdirectory(src/taskbar)
add_subdirectory(src/tray)
add_subdirectory(src/coreclient)
add_subdirectory(src/quicksettings)
add_subdirectory(src/media)
add_subdirectory(src/panel)
add_subdirectory(src/menu)
add_subdirectory(src/bg)
add_subdirectory(src/notify)
add_subdirectory(tests)

# --- data / session files ---------------------------------------------------
install(PROGRAMS src/session/helm-session
        DESTINATION ${CMAKE_INSTALL_PREFIX}/bin)
install(FILES data/wayland-sessions/hede.desktop
        DESTINATION ${CMAKE_INSTALL_PREFIX}/share/wayland-sessions)
install(DIRECTORY data/labwc
        DESTINATION ${CMAKE_INSTALL_PREFIX}/share/hede)
