#pragma once
#include <stdbool.h>
#include "vehicle_state.h"
#include "fair_v1_core.h"

bool occ_telemetry_snapshot(
    vehicle_state_t *snapshot,
    fair_v1_payload_t *payload,
    const char *vehicle_id
);
