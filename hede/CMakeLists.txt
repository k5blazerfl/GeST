cmake_minimum_required(VERSION 3.21)
project(hede VERSION 0.4.1 LANGUAGES C CXX)  # HeDE's own version line; the
# release source of truth — mirror-hede.py / amphi-hede.py stamp the HeDE repo
# tag and the gui-apps/hede ebuild from this. Bump it when cutting a HeDE change.

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

find_package(Qt6 REQUIRED COMPONENTS Widgets Test WaylandClient WaylandClientPrivate DBus)
find_package(LayerShellQt REQUIRED)
find_package(LibArchive REQUIRED) # hold-core's archive engine

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
add_subdirectory(src/theme)
add_subdirectory(src/decoration)
add_subdirectory(src/appearance)
add_subdirectory(src/panel)
add_subdirectory(src/menu)
add_subdirectory(src/bg)
add_subdirectory(src/notify)
add_subdirectory(src/sefe)
add_subdirectory(src/hold)
add_subdirectory(tests)

# --- data / session files ---------------------------------------------------
install(PROGRAMS src/session/helm-session
        DESTINATION ${CMAKE_INSTALL_PREFIX}/bin)
install(FILES data/wayland-sessions/hede.desktop
              data/wayland-sessions/hede-effects.desktop
        DESTINATION ${CMAKE_INSTALL_PREFIX}/share/wayland-sessions)
# Application launchers (the first per-app .desktop HeDE ships): helm-menu
# discovers these via the XDG app dirs; sefe also registers as the folder
# (inode/directory) handler.
install(FILES data/applications/sefe.desktop
              data/applications/hold.desktop
        DESTINATION ${CMAKE_INSTALL_PREFIX}/share/applications)
install(DIRECTORY data/labwc data/wayfire data/grub data/worlds
        DESTINATION ${CMAKE_INSTALL_PREFIX}/share/hede)
# The Helm labwc titlebar theme lands in the XDG theme search path
# (/usr/share/themes) so labwc resolves <theme><name>Helm</name>. helm-theme
# regenerates a per-user copy under ~/.local/share/themes that shadows this one.
install(DIRECTORY data/themes
        DESTINATION ${CMAKE_INSTALL_PREFIX}/share)
# The Plymouth boot splash (the Harbor scene).  Installed by the
# package so it exists in stage1 — catalyst's genkernel bakes it into the livecd
# initramfs (build_kernel runs before the root overlay), and the installer points
# an installed system's boot splash at it too.
install(DIRECTORY data/plymouth/hede
        DESTINATION ${CMAKE_INSTALL_PREFIX}/share/plymouth/themes)
