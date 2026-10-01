#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "uxr/client/client.h"
#include "fair_v1_core.h"
#define FAIR_DDS_SECURITY_C0 0
#define FAIR_DDS_SECURITY_C1 1
#define FAIR_DDS_SECURITY_C2 2
#define FAIR_DDS_XRCE_STREAM_BUFFER_BYTES 4096U
#define FAIR_DDS_XRCE_STREAM_HISTORY 8U
#define FAIR_DDS_ENQUEUE_ERR_MUTEX_TIMEOUT (-11)
#define FAIR_DDS_ENQUEUE_ERR_STREAM_REJECTED (-12)
#define FAIR_DDS_ENQUEUE_ERR_SLOT_MARK_FAILED (-13)
typedef void (*fair_dds_echo_callback_t)(void *context, uint32_t seq, int64_t t_ack_rx_us);
typedef struct {
    uxrUDPTransport udp_transport;
    uxrSession session;
    uxrStreamId reliable_out;
    uxrStreamId reliable_in;
    uint8_t reliable_out_buffer[FAIR_DDS_XRCE_STREAM_BUFFER_BYTES];
    uint8_t reliable_in_buffer[FAIR_DDS_XRCE_STREAM_BUFFER_BYTES];
    uxrObjectId telemetry_writer_id;
    uxrObjectId echo_reader_id;
    SemaphoreHandle_t session_mutex;
    TaskHandle_t session_task;
    volatile bool session_task_run;
    volatile bool session_created;
    volatile bool entities_ready;
    bool udp_initialized;
    char agent_ip[64];
    char agent_port[16];
    char serial_number[32];
    int security_level;
    fair_dds_echo_callback_t echo_callback;
    void *echo_callback_context;
} fair_dds_transport_t;
bool fair_dds_transport_init(fair_dds_transport_t *transport, const char *agent_ip, const char *agent_port, const char *serial_number, int security_level);
bool fair_dds_transport_start(fair_dds_transport_t *transport);
bool fair_dds_transport_ready(fair_dds_transport_t *transport);
bool fair_dds_transport_reconnect(fair_dds_transport_t *transport);
int fair_dds_transport_set_echo_callback(fair_dds_transport_t *transport, fair_dds_echo_callback_t callback, void *context);
int fair_dds_transport_enqueue_slot(fair_dds_transport_t *transport, fair_v1_slot_t *slot, const char *payload_data, int payload_len);
void fair_dds_transport_stop(fair_dds_transport_t *transport);
