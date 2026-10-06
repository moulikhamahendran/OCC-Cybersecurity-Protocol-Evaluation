#ifndef OCC_VEHICLE_STATE_H
#define OCC_VEHICLE_STATE_H

#include <stdbool.h>
#include <stdint.h>

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

#define OCC_VEHICLE_STATE_TEXT_LEN 16

typedef struct {
    uint32_t seq;
    int64_t t_source_us;

    float speed;
    float pos_x;
    float pos_y;
    float heading;
    float battery_pct;

    char state[OCC_VEHICLE_STATE_TEXT_LEN];
} vehicle_state_t;

/*
 * Start the physical ESP32 vehicle-state engine.
 *
 * IMPORTANT:
 * This task is independent from Wi-Fi, MQTT, OCC, and the dashboard.
 * Once started, VehicleState continues evolving even when transport
 * connectivity is unavailable.
 */
esp_err_t vehicle_state_start(uint32_t period_ms);

/*
 * Atomically read the latest vehicle state.
 */
bool vehicle_state_get(vehicle_state_t *out_state);

#ifdef __cplusplus
}
#endif

#endif
