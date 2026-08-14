qt_add_library(helm-coreclient STATIC
    coreclient.cpp
    updatepill.cpp
    networkpill.cpp
    batterypill.cpp
)
target_include_directories(helm-coreclient PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(helm-coreclient PUBLIC Qt6::Widgets Qt6::DBus)
