qt_add_executable(test-timefmt test_timefmt.cpp)
target_link_libraries(test-timefmt PRIVATE Qt6::Test helm-common)
add_test(NAME timefmt COMMAND test-timefmt)

qt_add_executable(test-config test_config.cpp)
target_link_libraries(test-config PRIVATE Qt6::Test helm-common)
add_test(NAME config COMMAND test-config)
