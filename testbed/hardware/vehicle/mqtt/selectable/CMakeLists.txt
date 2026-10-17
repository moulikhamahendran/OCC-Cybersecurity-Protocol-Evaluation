cmake_minimum_required(VERSION 3.16)

# OCC_UNIFIED_OPCUA_COMPONENTS_V1
set(EXTRA_COMPONENT_DIRS
    "${CMAKE_CURRENT_LIST_DIR}/../../../../hardware/esp32/fair_v1_core"
    "${CMAKE_CURRENT_LIST_DIR}/../../../../hardware/esp32/opcua/formal/fair_opcua_common"
    "${CMAKE_CURRENT_LIST_DIR}/../../../../hardware/esp32/opcua/c1/components/open62541lib"
)


# OCC_UNIFIED_DDS_BUILD_COMPONENTS_V1
list(APPEND EXTRA_COMPONENT_DIRS
    "${CMAKE_CURRENT_LIST_DIR}/../../../../hardware/esp32/dds/formal/fair_dds_common"
    "${CMAKE_CURRENT_LIST_DIR}/../../../../hardware/esp32/dds/formal/fair_dds_types"
    "${CMAKE_CURRENT_LIST_DIR}/../../../../hardware/esp32/dds/formal/.deps/microcdr"
    "${CMAKE_CURRENT_LIST_DIR}/../../../../hardware/esp32/dds/formal/.deps/microxrcedds"
)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)

project(occ_mqtt_runtime_selectable)

# OCC_OPCUA_BATCH2C_ASSETS: VM-001 only; never flash same key to VM-002.
set(OCC_VM001_ASSET_DIR
    "${CMAKE_CURRENT_LIST_DIR}/../../../../hardware/esp32/opcua/formal/c1/vehicle1/main/.generated")
foreach(asset esp32_client_cert.der esp32_client_key.der server_cert.der)
    if(NOT EXISTS "${OCC_VM001_ASSET_DIR}/${asset}")
        message(FATAL_ERROR "VM-001 OPC UA asset missing: ${asset}")
    endif()
endforeach()
target_add_binary_data(${PROJECT_NAME}.elf
    "${OCC_VM001_ASSET_DIR}/esp32_client_cert.der" BINARY
    RENAME_TO occ_opcua_client_cert)
target_add_binary_data(${PROJECT_NAME}.elf
    "${OCC_VM001_ASSET_DIR}/esp32_client_key.der" BINARY
    RENAME_TO occ_opcua_client_key)
target_add_binary_data(${PROJECT_NAME}.elf
    "${OCC_VM001_ASSET_DIR}/server_cert.der" BINARY
    RENAME_TO occ_opcua_server_cert)
