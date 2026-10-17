#include "telemetry_bridge.h"
#include <string.h>

bool occ_telemetry_snapshot(
    vehicle_state_t *snapshot,
    fair_v1_payload_t *payload,
    const char *vehicle_id
)
{
    if (!snapshot || !payload || !vehicle_id || !vehicle_id[0])
        return false;

    if (!vehicle_state_get(snapshot))
        return false;

    if (!memchr(snapshot->state, 0, sizeof(snapshot->state)) ||
        !snapshot->state[0])
        return false;

    memset(payload, 0, sizeof(*payload));

    payload->schema_ver = "runtime-1.0";
    payload->serialNumber = vehicle_id;
    payload->seq = snapshot->seq;
    payload->t_sched_us = snapshot->t_source_us;
    payload->speed = snapshot->speed;
    payload->pos_x = snapshot->pos_x;
    payload->pos_y = snapshot->pos_y;
    payload->heading = snapshot->heading;
    payload->battery_pct = snapshot->battery_pct;
    payload->state = snapshot->state;

    return true;
}
