#pragma once

#include "esp_err.h"

esp_err_t occ_opcua_c0_run(
    const char *vehicle_id,
    const char *endpoint
);

#include "protocol_selection.h"
/* Common runtime: retains C0 retry, telemetry and ack behavior. */
esp_err_t occ_opcua_run(const char *vehicle_id, const char *endpoint,
                        occ_security_t security);
