# hold-core — HeDE's archive engine (libarchive), shared by Seahorse and
# Hold-the-app. libarchive is a private impl detail; consumers see only Qt6::Core.
qt_add_library(hold-core STATIC holdcore.cpp)
target_include_directories(hold-core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(hold-core PUBLIC Qt6::Core PRIVATE LibArchive::LibArchive)
