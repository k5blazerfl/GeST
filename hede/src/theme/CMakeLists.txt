qt_add_library(helm-theme-lib STATIC
    theme.cpp
    world.cpp
)
target_include_directories(helm-theme-lib PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(helm-theme-lib PUBLIC Qt6::Core)

qt_add_executable(helm-theme main.cpp)
target_link_libraries(helm-theme PRIVATE Qt6::Core helm-theme-lib)
install(TARGETS helm-theme RUNTIME DESTINATION ${CMAKE_INSTALL_PREFIX}/bin)
