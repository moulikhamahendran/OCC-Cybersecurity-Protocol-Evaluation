#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "esp_err.h"
#include "mqtt_client.h"

#include "fair_v1_core.h"

#ifdef __cplusplus
extern "C" {
#endif

#define FAIR_V1_MQTT_TELEMETRY_TOPIC \
    "fair/v1/VM-001/telemetry"

#define FAIR_V1_MQTT_ECHO_TOPIC \
    "fair/v1/VM-001/echo"

#define FAIR_V1_MQTT_QOS 1

#define FAIR_V1_MQTT_MAX_ECHO_BYTES 128U

typedef void (*fair_mqtt_echo_callback_t)(
    void *context,
    uint32_t seq,
    int64_t t_ack_rx_us
);

typedef struct {
    const char *broker_uri;
    const char *serial_number;

    bool use_authentication;
    bool use_tls;

    const char *username;
    const char *password;
    const char *ca_certificate_pem;
} fair_mqtt_transport_config_t;

typedef struct {
    esp_mqtt_client_handle_t client;

    const char *serial_number;

    volatile bool connected;
    volatile bool echo_subscribed;

    int subscribe_msg_id;

    bool echo_reassembly_active;
    size_t echo_expected_len;
    size_t echo_received_len;

    char echo_buffer[
        FAIR_V1_MQTT_MAX_ECHO_BYTES
    ];

    fair_mqtt_echo_callback_t
        echo_callback;

    void *echo_callback_context;
} fair_mqtt_transport_t;

esp_err_t fair_mqtt_transport_init(
    fair_mqtt_transport_t *transport,
    const fair_mqtt_transport_config_t *config
);

esp_err_t fair_mqtt_transport_start(
    fair_mqtt_transport_t *transport
);

bool fair_mqtt_transport_ready(
    const fair_mqtt_transport_t *transport
);

esp_err_t fair_mqtt_transport_set_echo_callback(
    fair_mqtt_transport_t *transport,
    fair_mqtt_echo_callback_t callback,
    void *context
);

int fair_mqtt_transport_enqueue_slot(
    fair_mqtt_transport_t *transport,
    fair_v1_slot_t *slot,
    const char *payload_data,
    int payload_len
);

#ifdef __cplusplus
}
#endif
