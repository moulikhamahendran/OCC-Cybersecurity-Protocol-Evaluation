#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "fair_dds_types.h"

static bool fair_dds_valid_string(
    const char *value
)
{
    return
        value != NULL &&
        value[0] != '\0';
}

bool fair_dds_serialize_telemetry(
    ucdrBuffer *buffer,
    const fair_dds_telemetry_t *message
)
{
    if (
        buffer == NULL ||
        message == NULL ||
        !fair_dds_valid_string(
            message->schema_ver
        ) ||
        !fair_dds_valid_string(
            message->serialNumber
        ) ||
        message->state == NULL
    ) {
        return false;
    }

    return
        ucdr_serialize_string(
            buffer,
            message->schema_ver
        ) &&
        ucdr_serialize_string(
            buffer,
            message->serialNumber
        ) &&
        ucdr_serialize_uint32_t(
            buffer,
            message->seq
        ) &&
        ucdr_serialize_int64_t(
            buffer,
            message->t_sched_us
        ) &&
        ucdr_serialize_float(
            buffer,
            message->speed
        ) &&
        ucdr_serialize_float(
            buffer,
            message->pos_x
        ) &&
        ucdr_serialize_float(
            buffer,
            message->pos_y
        ) &&
        ucdr_serialize_float(
            buffer,
            message->heading
        ) &&
        ucdr_serialize_float(
            buffer,
            message->battery_pct
        ) &&
        ucdr_serialize_string(
            buffer,
            message->state
        );
}

bool fair_dds_deserialize_telemetry(
    ucdrBuffer *buffer,
    fair_dds_telemetry_rx_t *message
)
{
    if (
        buffer == NULL ||
        message == NULL ||
        message->schema_ver == NULL ||
        message->schema_ver_capacity == 0U ||
        message->serialNumber == NULL ||
        message->serialNumber_capacity == 0U ||
        message->state == NULL ||
        message->state_capacity == 0U
    ) {
        return false;
    }

    return
        ucdr_deserialize_string(
            buffer,
            message->schema_ver,
            message->schema_ver_capacity
        ) &&
        ucdr_deserialize_string(
            buffer,
            message->serialNumber,
            message->serialNumber_capacity
        ) &&
        ucdr_deserialize_uint32_t(
            buffer,
            &message->seq
        ) &&
        ucdr_deserialize_int64_t(
            buffer,
            &message->t_sched_us
        ) &&
        ucdr_deserialize_float(
            buffer,
            &message->speed
        ) &&
        ucdr_deserialize_float(
            buffer,
            &message->pos_x
        ) &&
        ucdr_deserialize_float(
            buffer,
            &message->pos_y
        ) &&
        ucdr_deserialize_float(
            buffer,
            &message->heading
        ) &&
        ucdr_deserialize_float(
            buffer,
            &message->battery_pct
        ) &&
        ucdr_deserialize_string(
            buffer,
            message->state,
            message->state_capacity
        );
}

bool fair_dds_serialize_echo(
    ucdrBuffer *buffer,
    const fair_dds_echo_t *message
)
{
    if (
        buffer == NULL ||
        message == NULL ||
        !fair_dds_valid_string(
            message->serialNumber
        )
    ) {
        return false;
    }

    return
        ucdr_serialize_string(
            buffer,
            message->serialNumber
        ) &&
        ucdr_serialize_uint32_t(
            buffer,
            message->seq
        );
}

bool fair_dds_deserialize_echo(
    ucdrBuffer *buffer,
    fair_dds_echo_rx_t *message
)
{
    if (
        buffer == NULL ||
        message == NULL ||
        message->serialNumber == NULL ||
        message->serialNumber_capacity == 0U
    ) {
        return false;
    }

    return
        ucdr_deserialize_string(
            buffer,
            message->serialNumber,
            message->serialNumber_capacity
        ) &&
        ucdr_deserialize_uint32_t(
            buffer,
            &message->seq
        );
}
