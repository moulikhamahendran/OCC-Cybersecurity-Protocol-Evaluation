#include <stddef.h>
#include <string.h>

#include "fair_v1_core.h"

int64_t fair_v1_schedule_time_us(
    int64_t run_t0_us,
    uint32_t seq
)
{
    return run_t0_us +
           ((int64_t)seq * FAIR_V1_PERIOD_US);
}

int64_t fair_v1_lateness_us(
    int64_t t_sched_us,
    int64_t t_send_us
)
{
    if (t_send_us <= t_sched_us) {
        return 0;
    }

    return t_send_us - t_sched_us;
}

bool fair_v1_seq_valid(
    uint32_t seq
)
{
    return seq < FAIR_V1_SLOT_COUNT;
}

int64_t fair_v1_run_end_us(
    int64_t run_t0_us
)
{
    return run_t0_us + FAIR_V1_RUN_DURATION_US;
}

uint32_t fair_v1_expired_slot_count(
    int64_t run_t0_us,
    int64_t now_us
)
{
    if (now_us <= run_t0_us) {
        return 0U;
    }

    int64_t elapsed_us =
        now_us - run_t0_us;

    uint64_t expired =
        (uint64_t)elapsed_us /
        (uint64_t)FAIR_V1_PERIOD_US;

    if (expired > FAIR_V1_SLOT_COUNT) {
        expired = FAIR_V1_SLOT_COUNT;
    }

    return (uint32_t)expired;
}

bool fair_v1_current_slot(
    int64_t run_t0_us,
    int64_t now_us,
    uint32_t *seq_out,
    int64_t *t_sched_out
)
{
    if (
        seq_out == NULL ||
        t_sched_out == NULL
    ) {
        return false;
    }

    if (
        now_us < run_t0_us ||
        now_us >= fair_v1_run_end_us(run_t0_us)
    ) {
        return false;
    }

    int64_t elapsed_us =
        now_us - run_t0_us;

    uint32_t seq =
        (uint32_t)(
            elapsed_us /
            FAIR_V1_PERIOD_US
        );

    if (!fair_v1_seq_valid(seq)) {
        return false;
    }

    *seq_out = seq;
    *t_sched_out =
        fair_v1_schedule_time_us(
            run_t0_us,
            seq
        );

    return true;
}

bool fair_v1_payload_init(
    fair_v1_payload_t *payload,
    const char *serial_number,
    const fair_v1_slot_t *slot,
    float speed,
    float pos_x,
    float pos_y,
    float heading,
    float battery_pct,
    const char *state
)
{
    if (
        payload == NULL ||
        serial_number == NULL ||
        slot == NULL ||
        state == NULL ||
        !fair_v1_seq_valid(slot->seq)
    ) {
        return false;
    }

    payload->schema_ver =
        FAIR_V1_PAYLOAD_SCHEMA_VERSION;

    payload->serialNumber =
        serial_number;

    payload->seq =
        slot->seq;

    payload->t_sched_us =
        slot->t_sched_us;

    payload->speed =
        speed;

    payload->pos_x =
        pos_x;

    payload->pos_y =
        pos_y;

    payload->heading =
        heading;

    payload->battery_pct =
        battery_pct;

    payload->state =
        state;

    return true;
}

bool fair_v1_payload_matches_slot(
    const fair_v1_payload_t *payload,
    const fair_v1_slot_t *slot
)
{
    if (
        payload == NULL ||
        slot == NULL ||
        payload->schema_ver == NULL ||
        payload->serialNumber == NULL ||
        payload->state == NULL
    ) {
        return false;
    }

    if (
        strcmp(
            payload->schema_ver,
            FAIR_V1_PAYLOAD_SCHEMA_VERSION
        ) != 0
    ) {
        return false;
    }

    if (
        !fair_v1_seq_valid(payload->seq) ||
        !fair_v1_seq_valid(slot->seq)
    ) {
        return false;
    }

    return
        payload->seq == slot->seq &&
        payload->t_sched_us == slot->t_sched_us;
}

bool fair_v1_slot_init(
    fair_v1_slot_t *slot,
    uint32_t seq,
    int64_t t_sched_us
)
{
    if (
        slot == NULL ||
        !fair_v1_seq_valid(seq)
    ) {
        return false;
    }

    slot->seq = seq;

    slot->t_sched_us = t_sched_us;
    slot->t_send_us = 0;
    slot->t_ack_rx_us = 0;
    slot->lateness_us = 0;

    /*
     * Status values are provisional until the corresponding
     * has_*_outcome flag becomes true.
     */
    slot->send_status =
        FAIR_V1_SEND_ON_TIME;

    slot->echo_status =
        FAIR_V1_ECHO_NOT_APPLICABLE;

    slot->skip_reason =
        FAIR_V1_SKIP_NONE;

    slot->has_t_send = false;
    slot->has_t_ack_rx = false;

    slot->has_send_outcome = false;
    slot->has_echo_outcome = false;

    return true;
}

bool fair_v1_slot_mark_skipped(
    fair_v1_slot_t *slot,
    fair_v1_skip_reason_t reason
)
{
    if (
        slot == NULL ||
        slot->has_send_outcome
    ) {
        return false;
    }

    if (
        reason != FAIR_V1_SKIP_SCHEDULER_OVERRUN &&
        reason != FAIR_V1_SKIP_RECONNECT
    ) {
        return false;
    }

    slot->send_status =
        FAIR_V1_SEND_SKIPPED;

    slot->echo_status =
        FAIR_V1_ECHO_NOT_APPLICABLE;

    slot->skip_reason = reason;

    slot->has_t_send = false;
    slot->has_t_ack_rx = false;

    slot->has_send_outcome = true;
    slot->has_echo_outcome = true;

    return true;
}

bool fair_v1_slot_mark_send_result(
    fair_v1_slot_t *slot,
    int64_t t_send_us,
    bool submission_success
)
{
    if (
        slot == NULL ||
        slot->has_send_outcome
    ) {
        return false;
    }

    slot->t_send_us = t_send_us;
    slot->has_t_send = true;

    slot->lateness_us =
        fair_v1_lateness_us(
            slot->t_sched_us,
            t_send_us
        );

    slot->skip_reason =
        FAIR_V1_SKIP_NONE;

    if (!submission_success) {
        slot->send_status =
            FAIR_V1_SEND_FAILED;

        slot->echo_status =
            FAIR_V1_ECHO_NOT_APPLICABLE;

        slot->has_send_outcome = true;
        slot->has_echo_outcome = true;

        return true;
    }

    if (
        slot->lateness_us >
        FAIR_V1_LATE_THRESHOLD_US
    ) {
        slot->send_status =
            FAIR_V1_SEND_LATE;
    } else {
        slot->send_status =
            FAIR_V1_SEND_ON_TIME;
    }

    slot->has_send_outcome = true;
    slot->has_echo_outcome = false;

    return true;
}

int64_t fair_v1_echo_deadline_us(
    int64_t t_send_us
)
{
    return t_send_us +
           FAIR_V1_ECHO_TIMEOUT_US;
}

bool fair_v1_slot_mark_timeout(
    fair_v1_slot_t *slot,
    int64_t now_us
)
{
    if (
        slot == NULL ||
        !slot->has_send_outcome ||
        !slot->has_t_send ||
        slot->has_t_ack_rx
    ) {
        return false;
    }

    if (
        slot->send_status != FAIR_V1_SEND_ON_TIME &&
        slot->send_status != FAIR_V1_SEND_LATE
    ) {
        return false;
    }

    if (
        now_us <
        fair_v1_echo_deadline_us(
            slot->t_send_us
        )
    ) {
        return false;
    }

    if (
        slot->has_echo_outcome &&
        slot->echo_status != FAIR_V1_ECHO_TIMEOUT
    ) {
        return false;
    }

    slot->echo_status =
        FAIR_V1_ECHO_TIMEOUT;

    slot->has_echo_outcome = true;

    return true;
}

bool fair_v1_slot_mark_echo_received(
    fair_v1_slot_t *slot,
    int64_t t_ack_rx_us
)
{
    if (
        slot == NULL ||
        !slot->has_send_outcome ||
        !slot->has_t_send ||
        slot->has_t_ack_rx
    ) {
        return false;
    }

    if (
        slot->send_status != FAIR_V1_SEND_ON_TIME &&
        slot->send_status != FAIR_V1_SEND_LATE
    ) {
        return false;
    }

    slot->t_ack_rx_us = t_ack_rx_us;
    slot->has_t_ack_rx = true;

    if (
        t_ack_rx_us >
        fair_v1_echo_deadline_us(
            slot->t_send_us
        )
    ) {
        slot->echo_status =
            FAIR_V1_ECHO_LATE_ECHO;
    } else {
        slot->echo_status =
            FAIR_V1_ECHO_OK;
    }

    slot->has_echo_outcome = true;

    return true;
}

const char *fair_v1_send_status_str(
    fair_v1_send_status_t status
)
{
    switch (status) {
        case FAIR_V1_SEND_ON_TIME:
            return "on_time";

        case FAIR_V1_SEND_LATE:
            return "late";

        case FAIR_V1_SEND_SKIPPED:
            return "skipped";

        case FAIR_V1_SEND_FAILED:
            return "send_failed";

        default:
            return NULL;
    }
}

const char *fair_v1_echo_status_str(
    fair_v1_echo_status_t status
)
{
    switch (status) {
        case FAIR_V1_ECHO_OK:
            return "ok";

        case FAIR_V1_ECHO_TIMEOUT:
            return "timeout";

        case FAIR_V1_ECHO_LATE_ECHO:
            return "late_echo";

        case FAIR_V1_ECHO_NOT_APPLICABLE:
            return "not_applicable";

        default:
            return NULL;
    }
}

const char *fair_v1_skip_reason_str(
    fair_v1_skip_reason_t reason
)
{
    switch (reason) {
        case FAIR_V1_SKIP_NONE:
            return "none";

        case FAIR_V1_SKIP_SCHEDULER_OVERRUN:
            return "scheduler_overrun";

        case FAIR_V1_SKIP_RECONNECT:
            return "reconnect";

        default:
            return NULL;
    }
}
