# SeFE — the Seahorse File Explorer. sefe-lib holds the pure (Core-only,
# unit-tested) helpers; the sefe executable is the themed Qt Widgets window.
qt_add_library(sefe-lib STATIC sefe.cpp)
target_include_directories(sefe-lib PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(sefe-lib PUBLIC Qt6::Core)

qt_add_executable(sefe main.cpp window.cpp)
target_link_libraries(sefe PRIVATE
    Qt6::Widgets
    sefe-lib
    helm-appearance
    helm-common
)
install(TARGETS sefe RUNTIME DESTINATION ${CMAKE_INSTALL_PREFIX}/bin)
