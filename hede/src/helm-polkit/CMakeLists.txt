# helm-polkit — HeDE's native PolicyKit authentication agent (replaces
# lxqt-policykit-agent). Binding-free: polkit's own C libraries (libpolkit-agent-1
# + libpolkit-gobject-1, from sys-auth/polkit) driving a Helm-themed Qt dialog —
# no polkit-qt. Qt's glib-backed event loop runs the agent's GObject signals.
find_package(PkgConfig REQUIRED)
pkg_check_modules(POLKITAGENT REQUIRED IMPORTED_TARGET polkit-agent-1 polkit-gobject-1)

qt_add_executable(helm-polkit
    main.cpp
    controller.cpp
    authdialog.cpp
    agentlistener.cpp)

# polkit gates its headers behind these "the API can change" acknowledgements.
# QT_NO_KEYWORDS: this target pulls in GLib/GObject headers, whose structs have a
# field named `signals` — Qt's `signals` keyword-macro would mangle it. Use the
# Q_SIGNALS/Q_SLOTS spellings here instead.
target_compile_definitions(helm-polkit PRIVATE
    QT_NO_KEYWORDS
    POLKIT_AGENT_I_KNOW_API_IS_SUBJECT_TO_CHANGE
    POLKIT_I_KNOW_API_IS_SUBJECT_TO_CHANGE)

target_link_libraries(helm-polkit PRIVATE
    Qt6::Widgets
    PkgConfig::POLKITAGENT
    helm-appearance)      # Helm palette on the auth dialog

install(TARGETS helm-polkit RUNTIME DESTINATION ${CMAKE_INSTALL_PREFIX}/bin)
