qt_add_library(helm-apps STATIC
    categories.cpp
    desktopentry.cpp
    launcherstore.cpp
    search.cpp
)
target_include_directories(helm-apps PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(helm-apps PUBLIC Qt6::Core)
