#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "esp_event.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "mqtt_client.h"

#include "fair_v1_core.h"
#include "fair_mqtt_codec.h"
#include "fair_mqtt_transport.h"

static const char *TAG =
    "FAIR_MQTT";

static void fair_mqtt_reset_echo_reassembly(
    fair_mqtt_transport_t *transport
)
{
    transport->echo_reassembly_active =
        false;

    transport->echo_expected_len =
        0U;

    transport->echo_received_len =
        0U;

    transport->echo_buffer[0] =
        '\0';
}

static bool fair_mqtt_topic_is_echo(
    const esp_mqtt_event_handle_t event
)
{
    if (
        event == NULL ||
        event->topic == NULL ||
        event->topic_len <= 0
    ) {
        return false;
    }

    const size_t expected_len =
        strlen(
            FAIR_V1_MQTT_ECHO_TOPIC
        );

    return
        (size_t)event->topic_len ==
            expected_len &&
        memcmp(
            event->topic,
            FAIR_V1_MQTT_ECHO_TOPIC,
            expected_len
        ) == 0;
}

static void fair_mqtt_handle_data(
    fair_mqtt_transport_t *transport,
    esp_mqtt_event_handle_t event
)
{
    if (
        transport == NULL ||
        event == NULL
    ) {
        return;
    }

    if (
        event->current_data_offset == 0
    ) {
        fair_mqtt_reset_echo_reassembly(
            transport
        );

        if (
            !fair_mqtt_topic_is_echo(
                event
            )
        ) {
            return;
        }

        if (
            event->total_data_len <= 0 ||
            (size_t)event->total_data_len >=
                sizeof(
                    transport->echo_buffer
                )
        ) {
            ESP_LOGW(
                TAG,
                "invalid echo length=%d",
                event->total_data_len
            );

            return;
        }

        transport->echo_reassembly_active =
            true;

        transport->echo_expected_len =
            (size_t)event->total_data_len;
    }

    if (
        !transport->echo_reassembly_active
    ) {
        return;
    }

    if (
        event->current_data_offset < 0 ||
        event->data_len < 0
    ) {
        fair_mqtt_reset_echo_reassembly(
            transport
        );

        return;
    }

    const size_t offset =
        (size_t)event->current_data_offset;

    const size_t fragment_len =
        (size_t)event->data_len;

    if (
        offset !=
            transport->echo_received_len ||
        offset + fragment_len >
            transport->echo_expected_len
    ) {
        ESP_LOGW(
            TAG,
            "invalid echo fragment"
        );

        fair_mqtt_reset_echo_reassembly(
            transport
        );

        return;
    }

    if (
        fragment_len > 0U &&
        event->data == NULL
    ) {
        fair_mqtt_reset_echo_reassembly(
            transport
        );

        return;
    }

    if (
        fragment_len > 0U
    ) {
        memcpy(
            transport->echo_buffer +
                offset,
            event->data,
            fragment_len
        );
    }

    transport->echo_received_len +=
        fragment_len;

    if (
        transport->echo_received_len !=
        transport->echo_expected_len
    ) {
        return;
    }

    /*
     * Frozen MQTT boundary:
     * capture candidate completion timestamp
     * immediately after final fragment copy and
     * before JSON decoding/correlation.
     */
    const int64_t t_ack_rx_us =
        esp_timer_get_time();

    transport->echo_buffer[
        transport->echo_received_len
    ] = '\0';

    uint32_t seq = 0U;

    const bool correlation_ok =
        fair_mqtt_decode_echo(
            transport->echo_buffer,
            transport->echo_received_len,
            transport->serial_number,
            &seq
        );

    if (
        correlation_ok &&
        transport->echo_callback != NULL
    ) {
        transport->echo_callback(
            transport->echo_callback_context,
            seq,
            t_ack_rx_us
        );
    } else if (!correlation_ok) {
        ESP_LOGW(
            TAG,
            "echo correlation rejected"
        );
    }

    fair_mqtt_reset_echo_reassembly(
        transport
    );
}

static void fair_mqtt_event_handler(
    void *handler_args,
    esp_event_base_t base,
    int32_t event_id,
    void *event_data
)
{
    (void)base;

    fair_mqtt_transport_t *transport =
        (fair_mqtt_transport_t *)
            handler_args;

    esp_mqtt_event_handle_t event =
        (esp_mqtt_event_handle_t)
            event_data;

    if (
        transport == NULL
    ) {
        return;
    }

    switch (
        (esp_mqtt_event_id_t)
            event_id
    ) {
        case MQTT_EVENT_CONNECTED:
            transport->connected =
                true;

            transport->echo_subscribed =
                false;

            transport->subscribe_msg_id =
                esp_mqtt_client_subscribe(
                    transport->client,
                    FAIR_V1_MQTT_ECHO_TOPIC,
                    FAIR_V1_MQTT_QOS
                );

            ESP_LOGI(
                TAG,
                "connected; echo subscribe rc=%d",
                transport->subscribe_msg_id
            );
            break;

        case MQTT_EVENT_SUBSCRIBED:
            if (
                event != NULL &&
                event->msg_id ==
                    transport->subscribe_msg_id
            ) {
                transport->echo_subscribed =
                    true;

                ESP_LOGI(
                    TAG,
                    "formal echo subscription active"
                );
            }
            break;

        case MQTT_EVENT_DISCONNECTED:
            transport->connected =
                false;

            transport->echo_subscribed =
                false;

            fair_mqtt_reset_echo_reassembly(
                transport
            );

            ESP_LOGW(
                TAG,
                "disconnected"
            );
            break;

        case MQTT_EVENT_DATA:
            fair_mqtt_handle_data(
                transport,
                event
            );
            break;

        case MQTT_EVENT_PUBLISHED:
            ESP_LOGD(
                TAG,
                "MQTT_EVENT_PUBLISHED msg_id=%d",
                event != NULL ?
                    event->msg_id :
                    -1
            );
            break;

        case MQTT_EVENT_ERROR:
            ESP_LOGE(
                TAG,
                "MQTT_EVENT_ERROR"
            );
            break;

        default:
            break;
    }
}

esp_err_t fair_mqtt_transport_init(
    fair_mqtt_transport_t *transport,
    const fair_mqtt_transport_config_t *config
)
{
    if (
        transport == NULL ||
        config == NULL ||
        config->broker_uri == NULL ||
        config->broker_uri[0] == '\0' ||
        config->serial_number == NULL ||
        config->serial_number[0] == '\0'
    ) {
        return ESP_ERR_INVALID_ARG;
    }

    if (
        config->use_authentication &&
        (
            config->username == NULL ||
            config->username[0] == '\0' ||
            config->password == NULL ||
            config->password[0] == '\0'
        )
    ) {
        return ESP_ERR_INVALID_ARG;
    }

    if (
        config->use_tls &&
        (
            config->ca_certificate_pem == NULL ||
            config->ca_certificate_pem[0] == '\0'
        )
    ) {
        return ESP_ERR_INVALID_ARG;
    }

    memset(
        transport,
        0,
        sizeof(*transport)
    );

    transport->serial_number =
        config->serial_number;

    transport->subscribe_msg_id =
        -1;

    fair_mqtt_reset_echo_reassembly(
        transport
    );

    esp_mqtt_client_config_t
        mqtt_config = {
            .broker.address.uri =
                config->broker_uri,
        };

    if (
        config->use_authentication
    ) {
        mqtt_config.credentials.username =
            config->username;

        mqtt_config
            .credentials
            .authentication
            .password =
                config->password;
    }

    if (
        config->use_tls
    ) {
        mqtt_config
            .broker
            .verification
            .certificate =
                config->ca_certificate_pem;
    }

    transport->client =
        esp_mqtt_client_init(
            &mqtt_config
        );

    if (
        transport->client == NULL
    ) {
        return ESP_FAIL;
    }

    esp_err_t err =
        esp_mqtt_client_register_event(
            transport->client,
            ESP_EVENT_ANY_ID,
            fair_mqtt_event_handler,
            transport
        );

    if (
        err != ESP_OK
    ) {
        esp_mqtt_client_destroy(
            transport->client
        );

        transport->client =
            NULL;

        return err;
    }

    return ESP_OK;
}

esp_err_t fair_mqtt_transport_start(
    fair_mqtt_transport_t *transport
)
{
    if (
        transport == NULL ||
        transport->client == NULL
    ) {
        return ESP_ERR_INVALID_ARG;
    }

    return esp_mqtt_client_start(
        transport->client
    );
}

bool fair_mqtt_transport_ready(
    const fair_mqtt_transport_t *transport
)
{
    if (
        transport == NULL
    ) {
        return false;
    }

    return
        transport->connected &&
        transport->echo_subscribed;
}

esp_err_t fair_mqtt_transport_set_echo_callback(
    fair_mqtt_transport_t *transport,
    fair_mqtt_echo_callback_t callback,
    void *context
)
{
    if (
        transport == NULL
    ) {
        return ESP_ERR_INVALID_ARG;
    }

    transport->echo_callback =
        callback;

    transport->echo_callback_context =
        context;

    return ESP_OK;
}

int fair_mqtt_transport_enqueue_slot(
    fair_mqtt_transport_t *transport,
    fair_v1_slot_t *slot,
    const char *payload_data,
    int payload_len
)
{
    if (
        transport == NULL ||
        transport->client == NULL ||
        slot == NULL ||
        payload_data == NULL ||
        payload_len <= 0 ||
        slot->has_send_outcome
    ) {
        return -1;
    }

    /*
     * Frozen MQTT send boundary.
     */
    const int64_t t_send_us =
        esp_timer_get_time();

    const int mqtt_enqueue_rc =
        esp_mqtt_client_enqueue(
            transport->client,
            FAIR_V1_MQTT_TELEMETRY_TOPIC,
            payload_data,
            payload_len,
            FAIR_V1_MQTT_QOS,
            0,
            false
        );

    const bool submission_success =
        mqtt_enqueue_rc >= 0;

    if (
        !fair_v1_slot_mark_send_result(
            slot,
            t_send_us,
            submission_success
        )
    ) {
        ESP_LOGE(
            TAG,
            "FAIR slot send-result update failed"
        );
    }

    return mqtt_enqueue_rc;
}
