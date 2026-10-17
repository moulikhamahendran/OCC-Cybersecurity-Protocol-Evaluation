#pragma once

#include <stdbool.h>
#include "esp_err.h"

typedef enum {
    OCC_PROTOCOL_MQTT = 0,
    OCC_PROTOCOL_OPCUA = 1,
    OCC_PROTOCOL_DDS = 2
} occ_protocol_t;

typedef enum {
    OCC_SECURITY_C0 = 0,
    OCC_SECURITY_C1 = 1,
    OCC_SECURITY_C2 = 2
} occ_security_t;

typedef struct {
    occ_protocol_t protocol;
    occ_security_t security;
} occ_protocol_selection_t;

bool occ_protocol_selection_valid(
    const occ_protocol_selection_t *selection
);

esp_err_t occ_protocol_selection_load(
    occ_protocol_selection_t *selection
);

esp_err_t occ_protocol_selection_save(
    const occ_protocol_selection_t *selection
);
