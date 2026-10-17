#pragma once

#include <stdbool.h>
#include "esp_err.h"
#include "protocol_selection.h"

typedef enum {
    OCC_RUNTIME_MQTT,
    OCC_RUNTIME_OPCUA_C0,
    OCC_RUNTIME_OPCUA_C1,
    OCC_RUNTIME_OPCUA_C2,
    OCC_RUNTIME_DDS_C0,
    OCC_RUNTIME_DDS_C1,
    OCC_RUNTIME_DDS_C2, /* OCC_DDS_C0_STREAM_V1 */
    OCC_RUNTIME_UNAVAILABLE
} occ_runtime_backend_t;

typedef struct {
    occ_protocol_selection_t selection;
    occ_runtime_backend_t backend;
    bool explicitly_configured;
} occ_protocol_manager_t;

esp_err_t occ_protocol_manager_resolve(
    occ_protocol_manager_t *manager,
    occ_security_t existing_mqtt_security
);
