qt_add_library(helm-appearance STATIC
    palette.cpp
    style.cpp
    icons.cpp
)
target_include_directories(helm-appearance PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
# Gui is public (QPalette in the header); Widgets is private (QApplication/style
# in applyAppearance only) so consumers/tests don't require QApplication.
# helm-theme-lib supplies the World loader (effectiveAccent sources the active
# world's accent). Qt6::Gui public (QPalette in the header); Widgets private
# (QApplication/style in applyAppearance only) so consumers/tests don't need it.
target_link_libraries(helm-appearance PUBLIC Qt6::Gui helm-common helm-theme-lib PRIVATE Qt6::Widgets)
