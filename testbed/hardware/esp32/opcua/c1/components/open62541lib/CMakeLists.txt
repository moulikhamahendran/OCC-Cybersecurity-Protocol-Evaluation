idf_component_register(
    SRCS "open62541.c"
    INCLUDE_DIRS "."
    PRIV_INCLUDE_DIRS
        "$ENV{IDF_PATH}/components/freertos/FreeRTOS-Kernel/include/freertos"
    REQUIRES
        freertos
        lwip
        mbedtls
)

target_compile_options(${COMPONENT_LIB} PRIVATE -Wno-error)


# Enable open62541 cryptography through ESP-IDF mbedTLS.
# PUBLIC is intentional: opcua_client.c also includes open62541.h
# and must see the same feature definition.
target_compile_definitions(${COMPONENT_LIB}
    PUBLIC
        UA_ENABLE_ENCRYPTION_MBEDTLS
)
