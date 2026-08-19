# The helm Qt Wayland client-side decoration plugin — painterly nine-patch window
# frames (opt-in via QT_WAYLAND_DECORATION=helm). Uses Qt's private WaylandClient
# decoration API (version-fragile by design; guarded to this Qt's version).

qt_add_plugin(helm-decoration CLASS_NAME HelmDecorationPlugin)
target_sources(helm-decoration PRIVATE
    helmdecorationplugin.cpp
    helmdecoration.cpp
)
set_target_properties(helm-decoration PROPERTIES AUTOMOC ON)
target_link_libraries(helm-decoration PRIVATE
    Qt6::Gui
    Qt6::WaylandClient
    Qt6::WaylandClientPrivate
    helm-common
    helm-theme-lib
)

# Install into the Qt wayland-decoration-client plugin dir so QT_WAYLAND_DECORATION
# can find it. (Shared with Qt's own plugins — standard for Qt plugins; on Gentoo
# HeDE and Qt share the /usr prefix.)
if(NOT DEFINED HELM_QT_PLUGIN_DIR)
    get_target_property(_helm_qmake Qt6::qmake IMPORTED_LOCATION)
    get_filename_component(_helm_qtbin "${_helm_qmake}" DIRECTORY)
    find_program(HELM_QTPATHS NAMES qtpaths6 qtpaths
        HINTS "${_helm_qtbin}" "${QT6_INSTALL_PREFIX}/bin"
        PATHS /usr/lib64/qt6/bin /usr/lib/qt6/bin)
    if(HELM_QTPATHS)
        execute_process(COMMAND ${HELM_QTPATHS} --query QT_INSTALL_PLUGINS
                        OUTPUT_VARIABLE HELM_QT_PLUGIN_DIR OUTPUT_STRIP_TRAILING_WHITESPACE)
    endif()
endif()
if(HELM_QT_PLUGIN_DIR)
    install(TARGETS helm-decoration
            LIBRARY DESTINATION "${HELM_QT_PLUGIN_DIR}/wayland-decoration-client")
else()
    message(WARNING "qtpaths not found — helm-decoration plugin will not be installed")
endif()
