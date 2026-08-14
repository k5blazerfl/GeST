qt_add_library(helm-bg-lib STATIC
    wallpaper.cpp
    backgroundwidget.cpp
)
target_include_directories(helm-bg-lib PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(helm-bg-lib PUBLIC Qt6::Widgets helm-common)

qt_add_executable(helm-bg main.cpp)
target_link_libraries(helm-bg PRIVATE
    Qt6::Widgets
    helm-bg-lib
    helm-wayland
    helm-common
)
install(TARGETS helm-bg RUNTIME DESTINATION ${CMAKE_INSTALL_PREFIX}/bin)
