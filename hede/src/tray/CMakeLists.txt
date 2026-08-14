qt_add_library(helm-tray STATIC
    snimodel.cpp
    sniwatcher.cpp
    trayitem.cpp
    traywidget.cpp
)
target_include_directories(helm-tray PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(helm-tray PUBLIC Qt6::Widgets Qt6::DBus)
