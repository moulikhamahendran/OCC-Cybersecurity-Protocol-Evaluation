#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "ucdr/microcdr.h"

#ifdef __cplusplus
extern "C" {
#endif

#define FAIR_DDS_TELEMETRY_TOPIC \
    "fair_v1_vm001_telemetry"

#define FAIR_DDS_ECHO_TOPIC \
    "fair_v1_vm001_echo"

#define FAIR_DDS_TELEMETRY_TYPE \
    "FairV1Telemetry"

#define FAIR_DDS_ECHO_TYPE \
    "FairV1Echo"

#define FAIR_DDS_SCHEMA_VERSION \
    "0.1"

typedef struct {
    const char *schema_ver;
    const char *serialNumber;

    uint32_t seq;
    int64_t t_sched_us;

    float speed;
    float pos_x;
    float pos_y;
    float heading;
    float battery_pct;

    const char *state;
} fair_dds_telemetry_t;

typedef struct {
    char *schema_ver;
    size_t schema_ver_capacity;

    char *serialNumber;
    size_t serialNumber_capacity;

    uint32_t seq;
    int64_t t_sched_us;

    float speed;
    float pos_x;
    float pos_y;
    float heading;
    float battery_pct;

    char *state;
    size_t state_capacity;
} fair_dds_telemetry_rx_t;

typedef struct {
    const char *serialNumber;
    uint32_t seq;
} fair_dds_echo_t;

typedef struct {
    char *serialNumber;
    size_t serialNumber_capacity;

    uint32_t seq;
} fair_dds_echo_rx_t;

bool fair_dds_serialize_telemetry(
    ucdrBuffer *buffer,
    const fair_dds_telemetry_t *message
);

bool fair_dds_deserialize_telemetry(
    ucdrBuffer *buffer,
    fair_dds_telemetry_rx_t *message
);

bool fair_dds_serialize_echo(
    ucdrBuffer *buffer,
    const fair_dds_echo_t *message
);

bool fair_dds_deserialize_echo(
    ucdrBuffer *buffer,
    fair_dds_echo_rx_t *message
);

#ifdef __cplusplus
}
#endif
