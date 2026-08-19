# hold-core — HeDE's archive engine (libarchive), shared by Seahorse and
# Hold-the-app. libarchive is a private impl detail; consumers see only Qt6::Core.
qt_add_library(hold-core STATIC holdcore.cpp archivemodel.cpp)
target_include_directories(hold-core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(hold-core PUBLIC Qt6::Core PRIVATE LibArchive::LibArchive)

# Hold — the standalone archive manager (H4), over the shared hold-core engine.
qt_add_executable(hold holdmain.cpp holdwindow.cpp)
target_link_libraries(hold PRIVATE Qt6::Widgets hold-core helm-appearance helm-common)
install(TARGETS hold RUNTIME DESTINATION ${CMAKE_INSTALL_PREFIX}/bin)
