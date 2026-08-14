qt_add_executable(test-timefmt test_timefmt.cpp)
target_link_libraries(test-timefmt PRIVATE Qt6::Test helm-common)
add_test(NAME timefmt COMMAND test-timefmt)

qt_add_executable(test-config test_config.cpp)
target_link_libraries(test-config PRIVATE Qt6::Test helm-common)
add_test(NAME config COMMAND test-config)

qt_add_executable(test-desktopentry test_desktopentry.cpp)
target_link_libraries(test-desktopentry PRIVATE Qt6::Test helm-apps)
add_test(NAME desktopentry COMMAND test-desktopentry)

qt_add_executable(test-toplevelmodel test_toplevelmodel.cpp)
target_link_libraries(test-toplevelmodel PRIVATE Qt6::Test helm-taskbar)
add_test(NAME toplevelmodel COMMAND test-toplevelmodel)

qt_add_executable(test-wallpaper test_wallpaper.cpp)
target_link_libraries(test-wallpaper PRIVATE Qt6::Test Qt6::Gui helm-bg-lib)
add_test(NAME wallpaper COMMAND test-wallpaper)

qt_add_executable(test-notification test_notification.cpp)
target_link_libraries(test-notification PRIVATE Qt6::Test helm-notify-lib)
add_test(NAME notification COMMAND test-notification)

qt_add_executable(test-snimodel test_snimodel.cpp)
target_link_libraries(test-snimodel PRIVATE Qt6::Test helm-tray)
add_test(NAME snimodel COMMAND test-snimodel)

# Headless integration: boot labwc (wlroots headless backend) and assert
# helm-panel binds a layer-shell surface. Skips (77) when labwc is absent.
add_test(NAME smoke-headless
    COMMAND ${CMAKE_CURRENT_SOURCE_DIR}/smoke-headless.sh $<TARGET_FILE:helm-panel>)
set_tests_properties(smoke-headless PROPERTIES
    LABELS integration
    SKIP_RETURN_CODE 77
    TIMEOUT 60)
