#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "esp_err.h"
#include "esp_log.h"
#include "esp_timer.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "open62541.h"

#include "fair_v1_core.h"
#include "fair_opcua_transport.h"
#include "fair_opcua_benchmark.h"

static const char *TAG =
    "FAIR_OPCUA_RUN";

typedef struct {
    bool initialized;

    UA_StatusCode submit_status;

    size_t logical_payload_bytes;
} fair_opcua_slot_diag_t;

static fair_v1_slot_t
    s_slots[
        FAIR_V1_SLOT_COUNT
    ];

static fair_opcua_slot_diag_t
    s_diag[
        FAIR_V1_SLOT_COUNT
    ];

static fair_opcua_request_context_t
    s_requests[
        FAIR_V1_SLOT_COUNT
    ];

static size_t fair_opcua_logical_payload_bytes(
    const fair_v1_payload_t *payload
)
{
    if (
        payload == NULL ||
        payload->schema_ver == NULL ||
        payload->serialNumber == NULL ||
        payload->state == NULL
    ) {
        return 0U;
    }

    return
        strlen(payload->schema_ver) +
        strlen(payload->serialNumber) +
        sizeof(uint32_t) +
        sizeof(int64_t) +
        (
            5U *
            sizeof(float)
        ) +
        strlen(payload->state);
}

static bool fair_opcua_init_slot(
    uint32_t seq,
    int64_t run_t0_us
)
{
    if (
        !fair_v1_seq_valid(seq)
    ) {
        return false;
    }

    if (
        s_diag[seq].initialized
    ) {
        return true;
    }

    if (
        !fair_v1_slot_init(
            &s_slots[seq],
            seq,
            fair_v1_schedule_time_us(
                run_t0_us,
                seq
            )
        )
    ) {
        return false;
    }

    s_diag[seq].initialized =
        true;

    s_diag[seq].submit_status =
        UA_STATUSCODE_BADNOTCONNECTED;

    s_diag[seq].logical_payload_bytes =
        0U;

    return true;
}

static void fair_opcua_process_timeouts(
    int64_t now_us
)
{
    for (
        uint32_t seq = 0U;
        seq < FAIR_V1_SLOT_COUNT;
        ++seq
    ) {
        if (
            !s_diag[seq].initialized
        ) {
            continue;
        }

        fair_v1_slot_t *slot =
            &s_slots[seq];

        if (
            slot->has_send_outcome &&
            !slot->has_echo_outcome &&
            slot->has_t_send &&
            (
                slot->send_status ==
                    FAIR_V1_SEND_ON_TIME ||
                slot->send_status ==
                    FAIR_V1_SEND_LATE
            )
        ) {
            if (
                now_us >=
                fair_v1_echo_deadline_us(
                    slot->t_send_us
                )
            ) {
                fair_v1_slot_mark_timeout(
                    slot,
                    now_us
                );
            }
        }
    }
}

static void fair_opcua_wait_until(
    fair_opcua_transport_t *transport,
    int64_t target_us
)
{
    while (true) {
        const int64_t now_us =
            esp_timer_get_time();

        if (
            now_us >= target_us
        ) {
            return;
        }

        fair_opcua_transport_iterate(
            transport,
            0U
        );

        fair_opcua_process_timeouts(
            now_us
        );

        const int64_t remaining_us =
            target_us -
            now_us;

        if (
            remaining_us >
            3000LL
        ) {
            int64_t sleep_ms =
                (
                    remaining_us -
                    1500LL
                ) /
                1000LL;

            if (
                sleep_ms < 1LL
            ) {
                sleep_ms = 1LL;
            }

            vTaskDelay(
                pdMS_TO_TICKS(
                    (uint32_t)sleep_ms
                )
            );
        } else {
            taskYIELD();
        }
    }
}

static void fair_opcua_format_i64(
    char *buffer,
    size_t buffer_size,
    bool present,
    int64_t value
)
{
    if (!present) {
        snprintf(
            buffer,
            buffer_size,
            "null"
        );

        return;
    }

    snprintf(
        buffer,
        buffer_size,
        "%" PRId64,
        value
    );
}

static void fair_opcua_emit_rows(
    const fair_opcua_benchmark_config_t *config
)
{
    uint32_t sent_success = 0U;
    uint32_t skipped = 0U;
    uint32_t send_failed = 0U;
    uint32_t echo_ok = 0U;
    uint32_t timeout = 0U;
    uint32_t late_echo = 0U;

    for (
        uint32_t seq = 0U;
        seq < FAIR_V1_SLOT_COUNT;
        ++seq
    ) {
        const fair_v1_slot_t *slot =
            &s_slots[seq];

        char t_send[32];
        char t_ack[32];
        char app_rtt[32];
        char schedule_latency[32];

        fair_opcua_format_i64(
            t_send,
            sizeof(t_send),
            slot->has_t_send,
            slot->t_send_us
        );

        fair_opcua_format_i64(
            t_ack,
            sizeof(t_ack),
            slot->has_t_ack_rx,
            slot->t_ack_rx_us
        );

        const bool has_rtt =
            slot->has_t_send &&
            slot->has_t_ack_rx;

        fair_opcua_format_i64(
            app_rtt,
            sizeof(app_rtt),
            has_rtt,
            has_rtt ?
                (
                    slot->t_ack_rx_us -
                    slot->t_send_us
                ) :
                0LL
        );

        fair_opcua_format_i64(
            schedule_latency,
            sizeof(schedule_latency),
            slot->has_t_ack_rx,
            slot->has_t_ack_rx ?
                (
                    slot->t_ack_rx_us -
                    slot->t_sched_us
                ) :
                0LL
        );

        if (
            s_diag[seq].submit_status ==
            UA_STATUSCODE_GOOD
        ) {
            ++sent_success;
        }

        if (
            slot->send_status ==
            FAIR_V1_SEND_SKIPPED
        ) {
            ++skipped;
        }

        if (
            slot->send_status ==
            FAIR_V1_SEND_FAILED
        ) {
            ++send_failed;
        }

        if (
            slot->echo_status ==
            FAIR_V1_ECHO_OK
        ) {
            ++echo_ok;
        }

        if (
            slot->echo_status ==
            FAIR_V1_ECHO_TIMEOUT
        ) {
            ++timeout;
        }

        if (
            slot->echo_status ==
            FAIR_V1_ECHO_LATE_ECHO
        ) {
            ++late_echo;
        }

        ESP_LOGI(
            TAG,
            "FAIR_RAW"
            "|dataset_schema_version=1.0"
            "|payload_schema_version=%s"
            "|run_id=%s"
            "|protocol=OPCUA"
            "|security_profile=%s"
            "|repeat_index=%" PRIu32
            "|serialNumber=%s"
            "|seq=%" PRIu32
            "|t_sched_us=%" PRId64
            "|t_send_us=%s"
            "|t_ack_rx_us=%s"
            "|app_rtt_us=%s"
            "|schedule_latency_us=%s"
            "|send_status=%s"
            "|echo_status=%s"
            "|skip_reason=%s"
            "|lateness_us=%" PRId64
            "|logical_payload_bytes=%u"
            "|wire_bytes=null"
            "|opcua_submit_status=0x%08" PRIx32
            "|latency_warmup_excluded=%s",
            FAIR_V1_PAYLOAD_SCHEMA_VERSION,
            config->run_id,
            config->profile_name,
            config->repeat_index,
            config->serial_number,
            seq,
            slot->t_sched_us,
            t_send,
            t_ack,
            app_rtt,
            schedule_latency,
            fair_v1_send_status_str(
                slot->send_status
            ),
            fair_v1_echo_status_str(
                slot->echo_status
            ),
            fair_v1_skip_reason_str(
                slot->skip_reason
            ),
            slot->lateness_us,
            (unsigned int)
                s_diag[seq]
                    .logical_payload_bytes,
            (uint32_t)
                s_diag[seq]
                    .submit_status,
            seq < 20U ?
                "true" :
                "false"
        );

        /*
         * Post-run reporting only:
         * allow IDLE0 to run while dumping FAIR_RAW rows.
         * Measurement timestamps are already frozen above.
         */
        vTaskDelay(1);
    }

    ESP_LOGI(
        TAG,
        "FAIR_SUMMARY"
        "|scheduled=%u"
        "|sent_success=%" PRIu32
        "|skipped=%" PRIu32
        "|send_failed=%" PRIu32
        "|echo_ok=%" PRIu32
        "|timeout=%" PRIu32
        "|late_echo=%" PRIu32
        "|achieved_rate=%.6f",
        (unsigned int)
            FAIR_V1_SLOT_COUNT,
        sent_success,
        skipped,
        send_failed,
        echo_ok,
        timeout,
        late_echo,
        ((double)sent_success) /
        ((double)FAIR_V1_SLOT_COUNT)
    );
}

esp_err_t fair_opcua_benchmark_run(
    fair_opcua_transport_t *transport,
    const fair_opcua_benchmark_config_t *config
)
{
    if (
        transport == NULL ||
        config == NULL ||
        config->run_id == NULL ||
        config->run_id[0] == '\0' ||
        config->profile_name == NULL ||
        config->profile_name[0] == '\0' ||
        config->serial_number == NULL ||
        config->serial_number[0] == '\0' ||
        config->state == NULL ||
        config->state[0] == '\0'
    ) {
        return
            ESP_ERR_INVALID_ARG;
    }

    if (
        !fair_opcua_transport_ready(
            transport
        )
    ) {
        return
            ESP_ERR_INVALID_STATE;
    }

    memset(
        s_slots,
        0,
        sizeof(s_slots)
    );

    memset(
        s_diag,
        0,
        sizeof(s_diag)
    );

    memset(
        s_requests,
        0,
        sizeof(s_requests)
    );

    const int64_t run_t0_us =
        esp_timer_get_time();

    uint32_t next_seq =
        FAIR_V1_FIRST_SEQ;

    ESP_LOGI(
        TAG,
        "run start t0=%" PRId64,
        run_t0_us
    );

    while (
        next_seq <
        FAIR_V1_SLOT_COUNT
    ) {
        const int64_t target_us =
            fair_v1_schedule_time_us(
                run_t0_us,
                next_seq
            );

        fair_opcua_wait_until(
            transport,
            target_us
        );

        bool reconnect_cause =
            false;

        if (
            !fair_opcua_transport_ready(
                transport
            )
        ) {
            reconnect_cause =
                true;

            fair_opcua_transport_reconnect(
                transport
            );
        }

        int64_t now_us =
            esp_timer_get_time();

        fair_opcua_process_timeouts(
            now_us
        );

        const uint32_t expired_count =
            fair_v1_expired_slot_count(
                run_t0_us,
                now_us
            );

        while (
            next_seq <
                expired_count &&
            next_seq <
                FAIR_V1_SLOT_COUNT
        ) {
            if (
                !fair_opcua_init_slot(
                    next_seq,
                    run_t0_us
                )
            ) {
                return ESP_FAIL;
            }

            const fair_v1_skip_reason_t reason =
                reconnect_cause ?
                    FAIR_V1_SKIP_RECONNECT :
                    FAIR_V1_SKIP_SCHEDULER_OVERRUN;

            if (
                !fair_v1_slot_mark_skipped(
                    &s_slots[next_seq],
                    reason
                )
            ) {
                return ESP_FAIL;
            }

            ++next_seq;
        }

        if (
            next_seq >=
            FAIR_V1_SLOT_COUNT
        ) {
            break;
        }

        if (
            !fair_opcua_init_slot(
                next_seq,
                run_t0_us
            )
        ) {
            return ESP_FAIL;
        }

        if (
            !fair_opcua_transport_ready(
                transport
            )
        ) {
            const int64_t expiry_us =
                target_us +
                FAIR_V1_PERIOD_US;

            while (
                esp_timer_get_time() <
                    expiry_us &&
                !fair_opcua_transport_ready(
                    transport
                )
            ) {
                fair_opcua_transport_iterate(
                    transport,
                    1U
                );

                vTaskDelay(
                    pdMS_TO_TICKS(1)
                );
            }

            if (
                !fair_opcua_transport_ready(
                    transport
                )
            ) {
                if (
                    !fair_v1_slot_mark_skipped(
                        &s_slots[next_seq],
                        FAIR_V1_SKIP_RECONNECT
                    )
                ) {
                    return ESP_FAIL;
                }

                ++next_seq;
                continue;
            }
        }

        fair_v1_payload_t payload;

        if (
            !fair_v1_payload_init(
                &payload,
                config->serial_number,
                &s_slots[next_seq],
                config->speed,
                config->pos_x,
                config->pos_y,
                config->heading,
                config->battery_pct,
                config->state
            )
        ) {
            return ESP_FAIL;
        }

        s_diag[next_seq]
            .logical_payload_bytes =
                fair_opcua_logical_payload_bytes(
                    &payload
                );

        const UA_StatusCode rc =
            fair_opcua_transport_submit(
                transport,
                &s_slots[next_seq],
                &payload,
                &s_requests[next_seq]
            );

        s_diag[next_seq]
            .submit_status =
                rc;

        fair_opcua_transport_iterate(
            transport,
            0U
        );

        ++next_seq;
    }

    const int64_t drain_deadline_us =
        fair_v1_run_end_us(
            run_t0_us
        ) +
        FAIR_V1_ECHO_TIMEOUT_US;

    while (
        esp_timer_get_time() <
        drain_deadline_us
    ) {
        fair_opcua_transport_iterate(
            transport,
            1U
        );

        fair_opcua_process_timeouts(
            esp_timer_get_time()
        );

        vTaskDelay(
            pdMS_TO_TICKS(1)
        );
    }

    fair_opcua_process_timeouts(
        drain_deadline_us
    );

    fair_opcua_transport_stop_callbacks(
        transport
    );

    fair_opcua_emit_rows(
        config
    );

    return ESP_OK;
}
