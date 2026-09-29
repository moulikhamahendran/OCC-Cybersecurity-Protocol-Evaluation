#pragma once

#include <stdint.h>

#include "esp_err.h"

#include "fair_opcua_transport.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    const char *run_id;
    const char *profile_name;

    uint32_t repeat_index;

    const char *serial_number;

    float speed;
    float pos_x;
    float pos_y;
    float heading;
    float battery_pct;

    const char *state;
} fair_opcua_benchmark_config_t;

esp_err_t fair_opcua_benchmark_run(
    fair_opcua_transport_t *transport,
    const fair_opcua_benchmark_config_t *config
);

#ifdef __cplusplus
}
#endif
