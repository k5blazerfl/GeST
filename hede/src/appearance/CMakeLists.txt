qt_add_library(helm-appearance STATIC
    palette.cpp
)
target_include_directories(helm-appearance PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
# Gui is public (QPalette in the header); Widgets is private (QApplication/style
# in applyAppearance only) so consumers/tests don't require QApplication.
target_link_libraries(helm-appearance PUBLIC Qt6::Gui helm-common PRIVATE Qt6::Widgets)
