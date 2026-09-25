idf_component_register(
    SRCS "open62541.c"
    INCLUDE_DIRS "."
    PRIV_INCLUDE_DIRS
        "$ENV{IDF_PATH}/components/freertos/FreeRTOS-Kernel/include/freertos"
    REQUIRES
        freertos
        lwip
)

target_compile_options(${COMPONENT_LIB} PRIVATE -Wno-error)
