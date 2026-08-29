# helm-pet — HeDE's native desktop pet (Hiedi's body).
#
# The one pure-C, non-Qt component: a lean wlr-layer-shell client that renders
# the pixel pet + a cairo/pango notification card, driven over a control FIFO by
# the Hiedi bridge (when installed). Generates its Wayland protocol glue with
# wayland-scanner rather than leaning on LayerShellQt like the Qt surfaces do.

find_program(WAYLAND_SCANNER wayland-scanner REQUIRED)
find_package(PkgConfig REQUIRED)
pkg_check_modules(WLPET REQUIRED wayland-client cairo pangocairo)

set(PROTO_DIR ${CMAKE_CURRENT_SOURCE_DIR}/protocols)
set(GEN ${CMAKE_CURRENT_BINARY_DIR}/gen)
file(MAKE_DIRECTORY ${GEN})

set(PET_PROTOCOLS
    wlr-layer-shell-unstable-v1
    xdg-shell
    wlr-foreign-toplevel-management-unstable-v1
    ext-idle-notify-v1
)

set(PET_PROTO_SRCS "")
foreach(proto ${PET_PROTOCOLS})
    add_custom_command(
        OUTPUT ${GEN}/${proto}-client-protocol.h
        COMMAND ${WAYLAND_SCANNER} client-header ${PROTO_DIR}/${proto}.xml ${GEN}/${proto}-client-protocol.h
        DEPENDS ${PROTO_DIR}/${proto}.xml
        VERBATIM)
    add_custom_command(
        OUTPUT ${GEN}/${proto}-protocol.c
        COMMAND ${WAYLAND_SCANNER} private-code ${PROTO_DIR}/${proto}.xml ${GEN}/${proto}-protocol.c
        DEPENDS ${PROTO_DIR}/${proto}.xml
        VERBATIM)
    list(APPEND PET_PROTO_SRCS ${GEN}/${proto}-protocol.c ${GEN}/${proto}-client-protocol.h)
endforeach()

add_executable(helm-pet helm-pet.c ${PET_PROTO_SRCS})
set_target_properties(helm-pet PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON)
target_include_directories(helm-pet PRIVATE ${GEN} ${CMAKE_CURRENT_SOURCE_DIR} ${WLPET_INCLUDE_DIRS})
target_compile_options(helm-pet PRIVATE -D_GNU_SOURCE ${WLPET_CFLAGS_OTHER})
target_link_libraries(helm-pet PRIVATE ${WLPET_LIBRARIES} m rt)

# ship + point the skin at its installed home
set(HELM_PET_SKINS ${CMAKE_INSTALL_PREFIX}/share/hede/helm-pet/pets)
target_compile_definitions(helm-pet PRIVATE PET_ASSET_DIR="${HELM_PET_SKINS}/neko")

install(TARGETS helm-pet RUNTIME DESTINATION ${CMAKE_INSTALL_PREFIX}/bin)
install(DIRECTORY pets/neko DESTINATION ${HELM_PET_SKINS})
