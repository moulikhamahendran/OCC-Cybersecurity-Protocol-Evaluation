idf_component_register(
    SRCS
        "main.c"
        "occ_management.c"
        "occ_opcua_provision_boot.c"
        "occ_unified_select_boot.c"
        "vehicle_state.c"
        "runtime_wifi.c"
        "runtime_mqtt_config.c"
        "runtime_endpoint_config.c"
        "runtime_known_wifi.c"

    INCLUDE_DIRS
        "."

    REQUIRES
        mbedtls
        mqtt
        fair_opcua_common
        fair_dds_common
        open62541lib
        json
        esp_wifi
        esp_event
        esp_netif
        nvs_flash
        wifi_provisioning
        esp_driver_gpio
        esp_driver_uart
        esp_timer
        lwip

    EMBED_TXTFILES
        "fair_v1_c2_ca.crt"
)

# Unified protocol selection module
target_sources(${COMPONENT_LIB} PRIVATE
    "${CMAKE_CURRENT_LIST_DIR}/../../../unified/protocol_selection.c"
)

target_include_directories(${COMPONENT_LIB} PRIVATE
    "${CMAKE_CURRENT_LIST_DIR}/../../../unified"
)

# OCC_UNIFIED_OPCUA_C0_ADAPTER_V1
target_sources(${COMPONENT_LIB} PRIVATE
    "${CMAKE_CURRENT_LIST_DIR}/../../../unified/opcua_c0_adapter.c"
    "${CMAKE_CURRENT_LIST_DIR}/../../../../../hardware/esp32/opcua/formal/c0/vehicle1/main/fair_opcua_profile.c"
)

target_include_directories(${COMPONENT_LIB} PRIVATE
    "${CMAKE_CURRENT_LIST_DIR}/../../../unified"
    "${CMAKE_CURRENT_LIST_DIR}/../../../../../hardware/esp32/opcua/formal/c0/vehicle1/main"
)

# OCC_UNIFIED_TELEMETRY_BRIDGE_V1
target_sources(${COMPONENT_LIB} PRIVATE
    "${CMAKE_CURRENT_LIST_DIR}/../../../unified/telemetry_bridge.c"
)

# OCC_DDS_C0_STREAM_V1
# Build only C0 runtime adapter; C1/C2 deferred until security testing.
target_sources(${COMPONENT_LIB} PRIVATE
    "${CMAKE_CURRENT_LIST_DIR}/../../../unified/dds_c0_runtime.c"
)

# OCC_UNIFIED_PROTOCOL_MANAGER_V1
target_sources(${COMPONENT_LIB} PRIVATE
    "${CMAKE_CURRENT_LIST_DIR}/../../../unified/protocol_manager.c"
)

# OCC_UNIFIED_OPCUA_RUNTIME_BATCH1_V1
target_sources(${COMPONENT_LIB} PRIVATE
    "${CMAKE_CURRENT_LIST_DIR}/../../../unified/opcua_c0_runtime.c"
)

# OCC_OPCUA_BATCH2C_SECURE_FACTORY: shared C0/C1/C2 adapter.
target_sources(${COMPONENT_LIB} PRIVATE
    "${CMAKE_CURRENT_LIST_DIR}/../../../unified/occ_opcua_secure_profile.c"
)
