#pragma once

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define FAIR_V1_PAYLOAD_SCHEMA_VERSION "0.1"

#define FAIR_V1_RATE_HZ              10U
#define FAIR_V1_PERIOD_US            100000LL
#define FAIR_V1_SLOT_COUNT           600U
#define FAIR_V1_FIRST_SEQ            0U
#define FAIR_V1_LAST_SEQ             599U
#define FAIR_V1_RUN_DURATION_US      60000000LL

#define FAIR_V1_LATE_THRESHOLD_US    1000LL
#define FAIR_V1_ECHO_TIMEOUT_US      1000000LL

typedef enum {
    FAIR_V1_SEND_ON_TIME = 0,
    FAIR_V1_SEND_LATE,
    FAIR_V1_SEND_SKIPPED,
    FAIR_V1_SEND_FAILED
} fair_v1_send_status_t;

typedef enum {
    FAIR_V1_ECHO_OK = 0,
    FAIR_V1_ECHO_TIMEOUT,
    FAIR_V1_ECHO_LATE_ECHO,
    FAIR_V1_ECHO_NOT_APPLICABLE
} fair_v1_echo_status_t;

typedef enum {
    FAIR_V1_SKIP_NONE = 0,
    FAIR_V1_SKIP_SCHEDULER_OVERRUN,
    FAIR_V1_SKIP_RECONNECT
} fair_v1_skip_reason_t;

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
} fair_v1_payload_t;

typedef struct {
    uint32_t seq;

    int64_t t_sched_us;
    int64_t t_send_us;
    int64_t t_ack_rx_us;
    int64_t lateness_us;

    fair_v1_send_status_t send_status;
    fair_v1_echo_status_t echo_status;
    fair_v1_skip_reason_t skip_reason;

    bool has_t_send;
    bool has_t_ack_rx;

    bool has_send_outcome;
    bool has_echo_outcome;
} fair_v1_slot_t;

int64_t fair_v1_schedule_time_us(
    int64_t run_t0_us,
    uint32_t seq
);

int64_t fair_v1_lateness_us(
    int64_t t_sched_us,
    int64_t t_send_us
);

bool fair_v1_seq_valid(
    uint32_t seq
);

int64_t fair_v1_run_end_us(
    int64_t run_t0_us
);

uint32_t fair_v1_expired_slot_count(
    int64_t run_t0_us,
    int64_t now_us
);

bool fair_v1_current_slot(
    int64_t run_t0_us,
    int64_t now_us,
    uint32_t *seq_out,
    int64_t *t_sched_out
);

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
);

bool fair_v1_payload_matches_slot(
    const fair_v1_payload_t *payload,
    const fair_v1_slot_t *slot
);

bool fair_v1_slot_init(
    fair_v1_slot_t *slot,
    uint32_t seq,
    int64_t t_sched_us
);

bool fair_v1_slot_mark_skipped(
    fair_v1_slot_t *slot,
    fair_v1_skip_reason_t reason
);

bool fair_v1_slot_mark_send_result(
    fair_v1_slot_t *slot,
    int64_t t_send_us,
    bool submission_success
);

int64_t fair_v1_echo_deadline_us(
    int64_t t_send_us
);

bool fair_v1_slot_mark_timeout(
    fair_v1_slot_t *slot,
    int64_t now_us
);

bool fair_v1_slot_mark_echo_received(
    fair_v1_slot_t *slot,
    int64_t t_ack_rx_us
);

const char *fair_v1_send_status_str(
    fair_v1_send_status_t status
);

const char *fair_v1_echo_status_str(
    fair_v1_echo_status_t status
);

const char *fair_v1_skip_reason_str(
    fair_v1_skip_reason_t reason
);

#ifdef __cplusplus
}
#endif
