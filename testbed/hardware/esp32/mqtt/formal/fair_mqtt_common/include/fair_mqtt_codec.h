#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "fair_v1_core.h"

#ifdef __cplusplus
extern "C" {
#endif

bool fair_mqtt_encode_payload(
    const fair_v1_payload_t *payload,
    char *output,
    size_t output_size,
    size_t *output_len
);

bool fair_mqtt_decode_echo(
    const char *json,
    size_t json_len,
    const char *expected_serial_number,
    uint32_t *seq_out
);

#ifdef __cplusplus
}
#endif
