set(
    LEGACY_CERT_DIR
    "${CMAKE_CURRENT_LIST_DIR}/../../../../c1/main/certs/c1"
)

set(
    GENERATED_CERT_DIR
    "${CMAKE_CURRENT_LIST_DIR}/.generated"
)

file(
    MAKE_DIRECTORY
    "${GENERATED_CERT_DIR}"
)

configure_file(
    "${LEGACY_CERT_DIR}/esp32_client_cert.der"
    "${GENERATED_CERT_DIR}/esp32_client_cert.der"
    COPYONLY
)

configure_file(
    "${LEGACY_CERT_DIR}/esp32_client_key.der"
    "${GENERATED_CERT_DIR}/esp32_client_key.der"
    COPYONLY
)

configure_file(
    "${LEGACY_CERT_DIR}/server_cert.der"
    "${GENERATED_CERT_DIR}/server_cert.der"
    COPYONLY
)

idf_component_register(
    SRCS
        "main.c"
        "fair_opcua_profile.c"
    INCLUDE_DIRS
        "."
    REQUIRES
        fair_opcua_common
        open62541lib
    EMBED_FILES
        ".generated/esp32_client_cert.der"
        ".generated/esp32_client_key.der"
        ".generated/server_cert.der"
)
