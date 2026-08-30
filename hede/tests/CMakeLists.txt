qt_add_executable(test-timefmt test_timefmt.cpp)
target_link_libraries(test-timefmt PRIVATE Qt6::Test helm-common)
add_test(NAME timefmt COMMAND test-timefmt)

qt_add_executable(test-config test_config.cpp)
target_link_libraries(test-config PRIVATE Qt6::Test helm-common)
add_test(NAME config COMMAND test-config)

qt_add_executable(test-barnacle test_barnacle.cpp)
target_link_libraries(test-barnacle PRIVATE Qt6::Test barnacle-lib)
add_test(NAME barnacle COMMAND test-barnacle)

qt_add_executable(test-desktopentry test_desktopentry.cpp)
target_link_libraries(test-desktopentry PRIVATE Qt6::Test helm-apps)
add_test(NAME desktopentry COMMAND test-desktopentry)

qt_add_executable(test-categories test_categories.cpp)
target_link_libraries(test-categories PRIVATE Qt6::Test helm-apps)
add_test(NAME categories COMMAND test-categories)

qt_add_executable(test-launcherstore test_launcherstore.cpp)
target_link_libraries(test-launcherstore PRIVATE Qt6::Test helm-apps)
add_test(NAME launcherstore COMMAND test-launcherstore)

qt_add_executable(test-search test_search.cpp)
target_link_libraries(test-search PRIVATE Qt6::Test helm-apps)
add_test(NAME search COMMAND test-search)

qt_add_executable(test-toplevelmodel test_toplevelmodel.cpp)
target_link_libraries(test-toplevelmodel PRIVATE Qt6::Test helm-taskbar)
add_test(NAME toplevelmodel COMMAND test-toplevelmodel)

qt_add_executable(test-identitymap test_identitymap.cpp)
target_link_libraries(test-identitymap PRIVATE Qt6::Test helm-taskbar)
add_test(NAME identitymap COMMAND test-identitymap)

qt_add_executable(test-wallpaper test_wallpaper.cpp)
target_link_libraries(test-wallpaper PRIVATE Qt6::Test Qt6::Gui helm-bg-lib)
add_test(NAME wallpaper COMMAND test-wallpaper)

qt_add_executable(test-notification test_notification.cpp)
target_link_libraries(test-notification PRIVATE Qt6::Test helm-notify-lib)
add_test(NAME notification COMMAND test-notification)

qt_add_executable(test-snimodel test_snimodel.cpp)
target_link_libraries(test-snimodel PRIVATE Qt6::Test helm-tray)
add_test(NAME snimodel COMMAND test-snimodel)

qt_add_executable(test-coreclient test_coreclient.cpp)
target_link_libraries(test-coreclient PRIVATE Qt6::Test helm-coreclient)
add_test(NAME coreclient COMMAND test-coreclient)

qt_add_executable(test-quicksettings test_quicksettings.cpp)
target_link_libraries(test-quicksettings PRIVATE Qt6::Test helm-quicksettings)
add_test(NAME quicksettings COMMAND test-quicksettings)

qt_add_executable(test-media test_media.cpp)
target_link_libraries(test-media PRIVATE Qt6::Test helm-media)
add_test(NAME media COMMAND test-media)

qt_add_executable(test-theme test_theme.cpp)
target_link_libraries(test-theme PRIVATE Qt6::Test helm-theme-lib)
# The committed Harbor-default assets must stay byte-identical to their generators.
target_compile_definitions(test-theme PRIVATE
    HELM_THEMERC_DEFAULT="${CMAKE_SOURCE_DIR}/data/themes/Helm/labwc/themerc"
    HELM_PLYMOUTH_DEFAULT="${CMAKE_SOURCE_DIR}/data/plymouth/hede/hede.script"
    HELM_GRUB_DEFAULT="${CMAKE_SOURCE_DIR}/data/grub/hede/theme.txt")
add_test(NAME theme COMMAND test-theme)

qt_add_executable(test-world test_world.cpp)
target_link_libraries(test-world PRIVATE Qt6::Test helm-theme-lib)
# Guard the shipped Slate world's professional intent (solid bar, no frame).
target_compile_definitions(test-world PRIVATE
    HELM_SLATE_THEME="${CMAKE_SOURCE_DIR}/data/worlds/slate/theme.yaml")
add_test(NAME world COMMAND test-world)

qt_add_executable(test-sefe test_sefe.cpp)
target_link_libraries(test-sefe PRIVATE Qt6::Test sefe-lib)
add_test(NAME sefe COMMAND test-sefe)

qt_add_executable(test-nineslice test_nineslice.cpp)
target_link_libraries(test-nineslice PRIVATE Qt6::Test Qt6::Gui helm-theme-lib)
add_test(NAME nineslice COMMAND test-nineslice)

qt_add_executable(test-appearance test_appearance.cpp)
target_link_libraries(test-appearance PRIVATE Qt6::Test Qt6::Widgets helm-appearance helm-theme-lib)
add_test(NAME appearance COMMAND test-appearance)

qt_add_executable(test-menu test_menu.cpp)
target_link_libraries(test-menu PRIVATE Qt6::Test helm-menu-lib)
add_test(NAME menu COMMAND test-menu)
# The per-style construction tests build real widgets — run headless.
set_tests_properties(menu PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen")

# Headless integration: boot labwc (wlroots headless backend) and assert
# helm-panel binds a layer-shell surface. Skips (77) when labwc is absent.
add_test(NAME smoke-headless
    COMMAND ${CMAKE_CURRENT_SOURCE_DIR}/smoke-headless.sh $<TARGET_FILE:helm-panel>)
set_tests_properties(smoke-headless PROPERTIES
    LABELS integration
    SKIP_RETURN_CODE 77
    TIMEOUT 60)

qt_add_executable(test-holdcore test_holdcore.cpp)
target_link_libraries(test-holdcore PRIVATE Qt6::Test hold-core)
add_test(NAME holdcore COMMAND test-holdcore)

qt_add_executable(test-ezra test_ezra.cpp)
target_link_libraries(test-ezra PRIVATE Qt6::Test ezra-lib)
add_test(NAME ezra COMMAND test-ezra)

qt_add_executable(test-autostart test_autostart.cpp)
target_link_libraries(test-autostart PRIVATE Qt6::Test helm-apps)
add_test(NAME autostart COMMAND test-autostart)
