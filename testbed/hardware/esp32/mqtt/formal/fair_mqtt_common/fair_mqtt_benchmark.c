#include <inttypes.h>
#include <limits.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "esp_log.h"
#include "esp_timer.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "fair_v1_core.h"
#include "fair_mqtt_codec.h"
#include "fair_mqtt_transport.h"
#include "fair_mqtt_benchmark.h"

static const char *TAG =
    "FAIR_MQTT_RUN";

#define FAIR_MQTT_PAYLOAD_BUFFER_BYTES 512U

typedef struct {
    bool initialized;

    size_t payload_bytes;

    int mqtt_enqueue_rc;
} fair_mqtt_slot_diag_t;

static fair_v1_slot_t
    s_slots[
        FAIR_V1_SLOT_COUNT
    ];

static fair_mqtt_slot_diag_t
    s_diag[
        FAIR_V1_SLOT_COUNT
    ];

static portMUX_TYPE s_slot_lock =
    portMUX_INITIALIZER_UNLOCKED;

static void fair_mqtt_wait_until(
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

        const int64_t remaining_us =
            target_us - now_us;

        if (
            remaining_us > 3000LL
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

static bool fair_mqtt_init_slot(
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

    const int64_t t_sched_us =
        fair_v1_schedule_time_us(
            run_t0_us,
            seq
        );

    if (
        !fair_v1_slot_init(
            &s_slots[seq],
            seq,
            t_sched_us
        )
    ) {
        return false;
    }

    s_diag[seq].initialized =
        true;

    s_diag[seq].payload_bytes =
        0U;

    s_diag[seq].mqtt_enqueue_rc =
        INT_MIN;

    return true;
}

static void fair_mqtt_echo_received(
    void *context,
    uint32_t seq,
    int64_t t_ack_rx_us
)
{
    (void)context;

    if (
        !fair_v1_seq_valid(seq)
    ) {
        return;
    }

    portENTER_CRITICAL(
        &s_slot_lock
    );

    if (
        s_diag[seq].initialized &&
        s_slots[seq].has_send_outcome &&
        (
            s_slots[seq].send_status ==
                FAIR_V1_SEND_ON_TIME ||
            s_slots[seq].send_status ==
                FAIR_V1_SEND_LATE
        )
    ) {
        if (
            !s_slots[seq].has_echo_outcome ||
            s_slots[seq].echo_status ==
                FAIR_V1_ECHO_TIMEOUT
        ) {
            fair_v1_slot_mark_echo_received(
                &s_slots[seq],
                t_ack_rx_us
            );
        }
    }

    portEXIT_CRITICAL(
        &s_slot_lock
    );
}

static void fair_mqtt_process_timeouts(
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

        portENTER_CRITICAL(
            &s_slot_lock
        );

        fair_v1_slot_t *slot =
            &s_slots[seq];

        if (
            slot->has_send_outcome &&
            !slot->has_echo_outcome &&
            (
                slot->send_status ==
                    FAIR_V1_SEND_ON_TIME ||
                slot->send_status ==
                    FAIR_V1_SEND_LATE
            ) &&
            slot->has_t_send
        ) {
            const int64_t deadline_us =
                fair_v1_echo_deadline_us(
                    slot->t_send_us
                );

            if (
                now_us >= deadline_us
            ) {
                fair_v1_slot_mark_timeout(
                    slot,
                    now_us
                );
            }
        }

        portEXIT_CRITICAL(
            &s_slot_lock
        );
    }
}

static bool fair_mqtt_all_echoes_final(
    void
)
{
    bool all_final = true;

    portENTER_CRITICAL(
        &s_slot_lock
    );

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

        const fair_v1_slot_t *slot =
            &s_slots[seq];

        if (
            slot->has_send_outcome &&
            (
                slot->send_status ==
                    FAIR_V1_SEND_ON_TIME ||
                slot->send_status ==
                    FAIR_V1_SEND_LATE
            ) &&
            !slot->has_echo_outcome
        ) {
            all_final = false;
            break;
        }
    }

    portEXIT_CRITICAL(
        &s_slot_lock
    );

    return all_final;
}

static const char *fair_mqtt_failure_reason(
    int mqtt_enqueue_rc
)
{
    if (
        mqtt_enqueue_rc == -1
    ) {
        return "enqueue_error";
    }

    if (
        mqtt_enqueue_rc == -2
    ) {
        return "outbox_full";
    }

    return "none";
}

static void fair_mqtt_format_optional_i64(
    char *buffer,
    size_t buffer_size,
    bool present,
    int64_t value
)
{
    if (
        !present
    ) {
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

static void fair_mqtt_emit_raw_rows(
    const fair_mqtt_benchmark_config_t *config
)
{
    uint32_t sent_messages = 0U;
    uint32_t skipped = 0U;
    uint32_t send_failed = 0U;
    uint32_t late = 0U;
    uint32_t echo_ok = 0U;
    uint32_t timeout = 0U;
    uint32_t late_echo = 0U;

    for (
        uint32_t seq = 0U;
        seq < FAIR_V1_SLOT_COUNT;
        ++seq
    ) {
        fair_v1_slot_t slot;

        portENTER_CRITICAL(
            &s_slot_lock
        );

        slot =
            s_slots[seq];

        portEXIT_CRITICAL(
            &s_slot_lock
        );

        char t_send[32];
        char t_ack[32];
        char app_rtt[32];
        char sched_latency[32];
        char mqtt_rc[32];

        fair_mqtt_format_optional_i64(
            t_send,
            sizeof(t_send),
            slot.has_t_send,
            slot.t_send_us
        );

        fair_mqtt_format_optional_i64(
            t_ack,
            sizeof(t_ack),
            slot.has_t_ack_rx,
            slot.t_ack_rx_us
        );

        const bool has_latency =
            slot.has_t_send &&
            slot.has_t_ack_rx;

        fair_mqtt_format_optional_i64(
            app_rtt,
            sizeof(app_rtt),
            has_latency,
            has_latency ?
                (
                    slot.t_ack_rx_us -
                    slot.t_send_us
                ) :
                0LL
        );

        fair_mqtt_format_optional_i64(
            sched_latency,
            sizeof(sched_latency),
            slot.has_t_ack_rx,
            slot.has_t_ack_rx ?
                (
                    slot.t_ack_rx_us -
                    slot.t_sched_us
                ) :
                0LL
        );

        if (
            s_diag[seq].mqtt_enqueue_rc ==
            INT_MIN
        ) {
            snprintf(
                mqtt_rc,
                sizeof(mqtt_rc),
                "null"
            );
        } else {
            snprintf(
                mqtt_rc,
                sizeof(mqtt_rc),
                "%d",
                s_diag[seq]
                    .mqtt_enqueue_rc
            );
        }

        if (
            s_diag[seq].mqtt_enqueue_rc >= 0
        ) {
            ++sent_messages;
        }

        if (
            slot.send_status ==
            FAIR_V1_SEND_SKIPPED
        ) {
            ++skipped;
        }

        if (
            slot.send_status ==
            FAIR_V1_SEND_FAILED
        ) {
            ++send_failed;
        }

        if (
            slot.send_status ==
            FAIR_V1_SEND_LATE
        ) {
            ++late;
        }

        if (
            slot.echo_status ==
            FAIR_V1_ECHO_OK
        ) {
            ++echo_ok;
        }

        if (
            slot.echo_status ==
            FAIR_V1_ECHO_TIMEOUT
        ) {
            ++timeout;
        }

        if (
            slot.echo_status ==
            FAIR_V1_ECHO_LATE_ECHO
        ) {
            ++late_echo;
        }

        ESP_LOGI(
            TAG,
            "FAIR_RAW|dataset_schema_version=1.0"
            "|payload_schema_version=%s"
            "|run_id=%s"
            "|protocol=MQTT"
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
            "|payload_bytes=%u"
            "|wire_bytes=null"
            "|mqtt_enqueue_rc=%s"
            "|send_failure_reason=%s"
            "|latency_warmup_excluded=%s",
            FAIR_V1_PAYLOAD_SCHEMA_VERSION,
            config->run_id,
            config->profile_name,
            config->repeat_index,
            config->serial_number,
            seq,
            slot.t_sched_us,
            t_send,
            t_ack,
            app_rtt,
            sched_latency,
            fair_v1_send_status_str(
                slot.send_status
            ),
            fair_v1_echo_status_str(
                slot.echo_status
            ),
            fair_v1_skip_reason_str(
                slot.skip_reason
            ),
            slot.lateness_us,
            (unsigned int)
                s_diag[seq]
                    .payload_bytes,
            mqtt_rc,
            fair_mqtt_failure_reason(
                s_diag[seq]
                    .mqtt_enqueue_rc
            ),
            seq < 20U ?
                "true" :
                "false"
        );
    }

    ESP_LOGI(
        TAG,
        "FAIR_SUMMARY"
        "|scheduled=%u"
        "|sent_success=%" PRIu32
        "|skipped=%" PRIu32
        "|send_failed=%" PRIu32
        "|late=%" PRIu32
        "|echo_ok=%" PRIu32
        "|timeout=%" PRIu32
        "|late_echo=%" PRIu32
        "|achieved_rate=%.6f",
        (unsigned int)
            FAIR_V1_SLOT_COUNT,
        sent_messages,
        skipped,
        send_failed,
        late,
        echo_ok,
        timeout,
        late_echo,
        ((double)sent_messages) / ((double)FAIR_V1_SLOT_COUNT)
    );
}

esp_err_t fair_mqtt_benchmark_run(
    fair_mqtt_transport_t *transport,
    const fair_mqtt_benchmark_config_t *config
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
        return ESP_ERR_INVALID_ARG;
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

    for (
        uint32_t i = 0U;
        i < FAIR_V1_SLOT_COUNT;
        ++i
    ) {
        s_diag[i].mqtt_enqueue_rc =
            INT_MIN;
    }

    esp_err_t err =
        fair_mqtt_transport_set_echo_callback(
            transport,
            fair_mqtt_echo_received,
            NULL
        );

    if (
        err != ESP_OK
    ) {
        return err;
    }

    /*
     * Setup/handshake is outside the measured run.
     * Wait for broker connection and successful
     * application-echo subscription first.
     */
    ESP_LOGI(
        TAG,
        "waiting for MQTT connection + echo subscription"
    );

    while (
        !fair_mqtt_transport_ready(
            transport
        )
    ) {
        vTaskDelay(
            pdMS_TO_TICKS(20)
        );
    }

    const int64_t run_t0_us =
        esp_timer_get_time();

    ESP_LOGI(
        TAG,
        "FAIR run start t0=%" PRId64,
        run_t0_us
    );

    uint32_t next_seq =
        FAIR_V1_FIRST_SEQ;

    while (
        next_seq <
        FAIR_V1_SLOT_COUNT
    ) {
        const int64_t target_us =
            fair_v1_schedule_time_us(
                run_t0_us,
                next_seq
            );

        fair_mqtt_wait_until(
            target_us
        );

        int64_t now_us =
            esp_timer_get_time();

        fair_mqtt_process_timeouts(
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
                !fair_mqtt_init_slot(
                    next_seq,
                    run_t0_us
                )
            ) {
                return ESP_FAIL;
            }

            const fair_v1_skip_reason_t reason =
                fair_mqtt_transport_ready(
                    transport
                ) ?
                    FAIR_V1_SKIP_SCHEDULER_OVERRUN :
                    FAIR_V1_SKIP_RECONNECT;

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
            !fair_mqtt_init_slot(
                next_seq,
                run_t0_us
            )
        ) {
            return ESP_FAIL;
        }

        /*
         * Frozen reconnect rule:
         *
         * If MQTT is unavailable at t_sched,
         * preserve the absolute schedule.
         *
         * The current slot may still be sent late
         * if the formal MQTT path becomes ready
         * before this slot expires.
         *
         * If no transmission can be attempted
         * before t_sched + one period, classify
         * the slot skipped/reconnect.
         */
        const int64_t slot_expiry_us =
            target_us +
            FAIR_V1_PERIOD_US;

        bool reconnect_blocked =
            false;

        if (
            !fair_mqtt_transport_ready(
                transport
            )
        ) {
            reconnect_blocked =
                true;

            while (
                !fair_mqtt_transport_ready(
                    transport
                ) &&
                esp_timer_get_time() <
                    slot_expiry_us
            ) {
                fair_mqtt_process_timeouts(
                    esp_timer_get_time()
                );

                vTaskDelay(
                    pdMS_TO_TICKS(1)
                );
            }
        }

        if (
            reconnect_blocked &&
            esp_timer_get_time() >=
                slot_expiry_us
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

        char encoded[
            FAIR_MQTT_PAYLOAD_BUFFER_BYTES
        ];

        size_t encoded_len = 0U;

        if (
            !fair_mqtt_encode_payload(
                &payload,
                encoded,
                sizeof(encoded),
                &encoded_len
            )
        ) {
            /*
             * Encoding/instrumentation failure is not
             * silently mapped onto a transport status.
             * The run must fail and later be INVALID.
             */
            ESP_LOGE(
                TAG,
                "payload encoding failed seq=%" PRIu32,
                next_seq
            );

            return ESP_FAIL;
        }

        s_diag[next_seq].payload_bytes =
            encoded_len;

        const int mqtt_enqueue_rc =
            fair_mqtt_transport_enqueue_slot(
                transport,
                &s_slots[next_seq],
                encoded,
                (int)encoded_len
            );

        s_diag[next_seq].mqtt_enqueue_rc =
            mqtt_enqueue_rc;

        ++next_seq;
    }

    /*
     * Final drain is capped at one echo timeout
     * after formal run end.
     */
    const int64_t drain_deadline_us =
        fair_v1_run_end_us(
            run_t0_us
        ) +
        FAIR_V1_ECHO_TIMEOUT_US;

    while (
        esp_timer_get_time() <
            drain_deadline_us &&
        !fair_mqtt_all_echoes_final()
    ) {
        fair_mqtt_process_timeouts(
            esp_timer_get_time()
        );

        vTaskDelay(
            pdMS_TO_TICKS(10)
        );
    }

    fair_mqtt_process_timeouts(
        drain_deadline_us
    );

    /*
     * Stop accepting new echo updates after the
     * frozen drain boundary, then emit one record
     * for all 600 scheduled slots.
     */
    fair_mqtt_transport_set_echo_callback(
        transport,
        NULL,
        NULL
    );

    fair_mqtt_emit_raw_rows(
        config
    );

    return ESP_OK;
}
