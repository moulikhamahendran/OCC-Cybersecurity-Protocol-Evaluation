#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "ucdr/microcdr.h"
#include "fair_dds_types.h"
#include "fair_dds_codec.h"

bool fair_dds_encode_payload(const fair_v1_payload_t *payload, char *output, size_t output_capacity, size_t *encoded_len)
{
    if (!payload || !output || output_capacity == 0U || !encoded_len) return false;
    fair_dds_telemetry_t m = {
        .schema_ver=payload->schema_ver, .serialNumber=payload->serialNumber,
        .seq=payload->seq, .t_sched_us=payload->t_sched_us,
        .speed=payload->speed, .pos_x=payload->pos_x, .pos_y=payload->pos_y,
        .heading=payload->heading, .battery_pct=payload->battery_pct, .state=payload->state,
    };
    ucdrBuffer ub;
    ucdr_init_buffer(&ub, (uint8_t*)output, output_capacity);
    if (!fair_dds_serialize_telemetry(&ub, &m)) return false;
    *encoded_len = ucdr_buffer_length(&ub);
    return *encoded_len > 0U && *encoded_len <= output_capacity;
}

bool fair_dds_decode_echo(const char *data, size_t data_len, const char *expected_serial_number, uint32_t *seq_out)
{
    if (!data || data_len == 0U || !expected_serial_number || !seq_out) return false;
    char serial[64] = {0};
    fair_dds_echo_rx_t e = {.serialNumber=serial, .serialNumber_capacity=sizeof(serial), .seq=0U};
    ucdrBuffer ub;
    ucdr_init_buffer(&ub, (uint8_t*)data, data_len);
    if (!fair_dds_deserialize_echo(&ub, &e)) return false;
    if (strcmp(e.serialNumber, expected_serial_number) != 0) return false;
    *seq_out = e.seq;
    return true;
}
