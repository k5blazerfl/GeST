qt_add_library(helm-notify-lib STATIC
    notification.cpp
    toast.cpp
    notifyservice.cpp
    notifyadaptor.cpp
)
target_include_directories(helm-notify-lib PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(helm-notify-lib PUBLIC Qt6::Widgets Qt6::DBus helm-common)

qt_add_executable(helm-notifyd main.cpp)
target_link_libraries(helm-notifyd PRIVATE
    Qt6::Widgets
    Qt6::DBus
    helm-notify-lib
    helm-wayland
    helm-appearance
    helm-common
)
install(TARGETS helm-notifyd RUNTIME DESTINATION ${CMAKE_INSTALL_PREFIX}/bin)
