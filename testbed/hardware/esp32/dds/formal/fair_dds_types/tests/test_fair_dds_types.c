#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "ucdr/microcdr.h"

#include "fair_dds_types.h"

static void test_telemetry(void)
{
    uint8_t storage[512] = {0};

    ucdrBuffer writer;

    ucdr_init_buffer(
        &writer,
        storage,
        sizeof(storage)
    );

    const fair_dds_telemetry_t tx = {
        .schema_ver = "0.1",
        .serialNumber = "VM-001",
        .seq = 123U,
        .t_sched_us = 12300000LL,

        .speed = 1.0f,
        .pos_x = 2.0f,
        .pos_y = 3.0f,
        .heading = 4.0f,
        .battery_pct = 80.0f,

        .state = "RUNNING",
    };

    assert(
        fair_dds_serialize_telemetry(
            &writer,
            &tx
        )
    );

    const size_t encoded_len =
        ucdr_buffer_length(
            &writer
        );

    assert(encoded_len > 0U);
    assert(encoded_len < sizeof(storage));

    char schema_ver[16] = {0};
    char serial_number[32] = {0};
    char state[64] = {0};

    fair_dds_telemetry_rx_t rx = {
        .schema_ver =
            schema_ver,

        .schema_ver_capacity =
            sizeof(schema_ver),

        .serialNumber =
            serial_number,

        .serialNumber_capacity =
            sizeof(serial_number),

        .state =
            state,

        .state_capacity =
            sizeof(state),
    };

    ucdrBuffer reader;

    ucdr_init_buffer(
        &reader,
        storage,
        encoded_len
    );

    assert(
        fair_dds_deserialize_telemetry(
            &reader,
            &rx
        )
    );

    assert(
        strcmp(
            rx.schema_ver,
            "0.1"
        ) == 0
    );

    assert(
        strcmp(
            rx.serialNumber,
            "VM-001"
        ) == 0
    );

    assert(rx.seq == 123U);
    assert(rx.t_sched_us == 12300000LL);

    assert(rx.speed == 1.0f);
    assert(rx.pos_x == 2.0f);
    assert(rx.pos_y == 3.0f);
    assert(rx.heading == 4.0f);
    assert(rx.battery_pct == 80.0f);

    assert(
        strcmp(
            rx.state,
            "RUNNING"
        ) == 0
    );

    printf(
        "TELEMETRY_CDR_BYTES=%zu\n",
        encoded_len
    );
}

static void test_echo(void)
{
    uint8_t storage[128] = {0};

    ucdrBuffer writer;

    ucdr_init_buffer(
        &writer,
        storage,
        sizeof(storage)
    );

    const fair_dds_echo_t tx = {
        .serialNumber = "VM-001",
        .seq = 123U,
    };

    assert(
        fair_dds_serialize_echo(
            &writer,
            &tx
        )
    );

    const size_t encoded_len =
        ucdr_buffer_length(
            &writer
        );

    char serial_number[32] = {0};

    fair_dds_echo_rx_t rx = {
        .serialNumber =
            serial_number,

        .serialNumber_capacity =
            sizeof(serial_number),
    };

    ucdrBuffer reader;

    ucdr_init_buffer(
        &reader,
        storage,
        encoded_len
    );

    assert(
        fair_dds_deserialize_echo(
            &reader,
            &rx
        )
    );

    assert(
        strcmp(
            rx.serialNumber,
            "VM-001"
        ) == 0
    );

    assert(rx.seq == 123U);

    printf(
        "ECHO_CDR_BYTES=%zu\n",
        encoded_len
    );
}

int main(void)
{
    test_telemetry();
    test_echo();

    puts(
        "FAIR_V1_DDS_CDR_ROUNDTRIP: PASS"
    );

    return 0;
}
