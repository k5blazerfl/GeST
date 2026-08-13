qt_add_executable(test-timefmt test_timefmt.cpp)
target_link_libraries(test-timefmt PRIVATE Qt6::Test helm-common)
add_test(NAME timefmt COMMAND test-timefmt)

qt_add_executable(test-config test_config.cpp)
target_link_libraries(test-config PRIVATE Qt6::Test helm-common)
add_test(NAME config COMMAND test-config)

# Headless integration: boot labwc (wlroots headless backend) and assert
# helm-panel binds a layer-shell surface. Skips (77) when labwc is absent.
add_test(NAME smoke-headless
    COMMAND ${CMAKE_CURRENT_SOURCE_DIR}/smoke-headless.sh $<TARGET_FILE:helm-panel>)
set_tests_properties(smoke-headless PROPERTIES
    LABELS integration
    SKIP_RETURN_CODE 77
    TIMEOUT 60)
