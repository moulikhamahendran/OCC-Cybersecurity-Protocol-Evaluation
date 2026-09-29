#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "fair_v1_core.h"
#define FAIR_DDS_PAYLOAD_BUFFER_BYTES 512U
#define FAIR_DDS_ECHO_BUFFER_BYTES 128U
bool fair_dds_encode_payload(const fair_v1_payload_t *payload, char *output, size_t output_capacity, size_t *encoded_len);
bool fair_dds_decode_echo(const char *data, size_t data_len, const char *expected_serial_number, uint32_t *seq_out);
