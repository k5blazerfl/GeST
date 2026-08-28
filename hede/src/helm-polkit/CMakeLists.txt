# helm-polkit — HeDE's native PolicyKit authentication agent (replaces
# lxqt-policykit-agent). Qt Widgets + polkit-qt-1 (Qt6); themed via helm-appearance.
find_package(PolkitQt6-1 REQUIRED)

qt_add_executable(helm-polkit
    main.cpp
    agent.cpp
    authdialog.cpp)

target_link_libraries(helm-polkit PRIVATE
    Qt6::Widgets
    PolkitQt6-1::Agent
    PolkitQt6-1::Core
    helm-appearance)      # Helm palette on the auth dialog

install(TARGETS helm-polkit RUNTIME DESTINATION ${CMAKE_INSTALL_PREFIX}/bin)
