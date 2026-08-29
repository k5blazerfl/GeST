qt_add_library(helm-apps STATIC
    categories.cpp
    desktopentry.cpp
    launcherstore.cpp
    search.cpp
    autostart.cpp
)
target_include_directories(helm-apps PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(helm-apps PUBLIC Qt6::Core)

# The session's XDG autostart runner (launched from the labwc autostart file).
qt_add_executable(helm-autostart autostart-main.cpp)
target_link_libraries(helm-autostart PRIVATE helm-apps helm-common)
install(TARGETS helm-autostart RUNTIME DESTINATION ${CMAKE_INSTALL_PREFIX}/bin)
