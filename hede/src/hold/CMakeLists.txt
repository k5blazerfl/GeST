# hold-core — HeDE's archive engine (libarchive), the shared heart of Hold.
# Seahorse (SeFE) consumes it directly for browse-in-place + the rich extract ops;
# there is no separate Hold binary — Hold lives inside the capital ship. libarchive
# is a private impl detail; consumers see only Qt6::Core. See docs/design/hold.md.
qt_add_library(hold-core STATIC holdcore.cpp archivemodel.cpp job.cpp)
target_include_directories(hold-core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(hold-core PUBLIC Qt6::Core PRIVATE LibArchive::LibArchive)
