#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "cJSON.h"

#include "esp_err.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "mqtt_client.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "fair_mqtt_network.h"


#define OCC_MQTT_QOS 1
#define TOPIC_BUFFER_BYTES 128
#define PAYLOAD_BUFFER_BYTES 384
#define ECHO_BUFFER_BYTES 192

static const char *TAG = "OCC_MQTT_RUNTIME";

static esp_mqtt_client_handle_t s_client = NULL;

static volatile bool s_mqtt_connected = false;
static volatile bool s_echo_subscribed = false;

static char s_telemetry_topic[TOPIC_BUFFER_BYTES];
static char s_echo_topic[TOPIC_BUFFER_BYTES];

static char s_echo_buffer[ECHO_BUFFER_BYTES];
static size_t s_echo_expected_len = 0U;
static size_t s_echo_received_len = 0U;
static bool s_echo_active = false;

static uint64_t s_echo_count = 0U;


static void reset_echo_reassembly(void)
{
    s_echo_expected_len = 0U;
    s_echo_received_len = 0U;
    s_echo_active = false;
    s_echo_buffer[0] = '\0';
}


static bool topic_matches(
    const char *event_topic,
    int event_topic_len,
    const char *expected
)
{
    if (
        event_topic == NULL ||
        expected == NULL ||
        event_topic_len < 0
    ) {
        return false;
    }

    const size_t expected_len = strlen(expected);

    return
        expected_len == (size_t)event_topic_len &&
        memcmp(
            event_topic,
            expected,
            expected_len
        ) == 0;
}


static void handle_complete_echo(void)
{
    cJSON *root =
        cJSON_ParseWithLength(
            s_echo_buffer,
            s_echo_received_len
        );

    if (root == NULL) {
        ESP_LOGW(
            TAG,
            "invalid echo JSON"
        );
        return;
    }

    const cJSON *serial =
        cJSON_GetObjectItemCaseSensitive(
            root,
            "serialNumber"
        );

    const cJSON *seq =
        cJSON_GetObjectItemCaseSensitive(
            root,
            "seq"
        );

    const bool valid =
        cJSON_IsString(serial) &&
        serial->valuestring != NULL &&
        strcmp(
            serial->valuestring,
            CONFIG_OCC_VEHICLE_ID
        ) == 0 &&
        cJSON_IsNumber(seq) &&
        seq->valuedouble >= 0.0;

    if (valid) {
        ++s_echo_count;

        ESP_LOGI(
            TAG,
            "echo vehicle=%s seq=%.0f total_echo=%" PRIu64,
            serial->valuestring,
            seq->valuedouble,
            s_echo_count
        );
    } else {
        ESP_LOGW(
            TAG,
            "echo validation failed"
        );
    }

    cJSON_Delete(root);
}


static void handle_echo_fragment(
    esp_mqtt_event_handle_t event
)
{
    if (event == NULL) {
        return;
    }

    if (event->current_data_offset == 0) {
        reset_echo_reassembly();

        if (
            !topic_matches(
                event->topic,
                event->topic_len,
                s_echo_topic
            )
        ) {
            return;
        }

        if (
            event->total_data_len <= 0 ||
            event->total_data_len >=
                (int)sizeof(s_echo_buffer)
        ) {
            ESP_LOGW(
                TAG,
                "echo too large total=%d",
                event->total_data_len
            );
            return;
        }

        s_echo_expected_len =
            (size_t)event->total_data_len;

        s_echo_active = true;
    }

    if (!s_echo_active) {
        return;
    }

    if (
        event->current_data_offset < 0 ||
        event->data_len < 0
    ) {
        reset_echo_reassembly();
        return;
    }

    const size_t offset =
        (size_t)event->current_data_offset;

    const size_t fragment_len =
        (size_t)event->data_len;

    if (
        offset != s_echo_received_len ||
        offset + fragment_len >
            s_echo_expected_len ||
        offset + fragment_len >=
            sizeof(s_echo_buffer)
    ) {
        ESP_LOGW(
            TAG,
            "invalid echo fragment"
        );

        reset_echo_reassembly();
        return;
    }

    memcpy(
        s_echo_buffer + offset,
        event->data,
        fragment_len
    );

    s_echo_received_len += fragment_len;

    if (
        s_echo_received_len !=
        s_echo_expected_len
    ) {
        return;
    }

    s_echo_buffer[s_echo_received_len] =
        '\0';

    handle_complete_echo();

    reset_echo_reassembly();
}


static void mqtt_event_handler(
    void *handler_args,
    esp_event_base_t base,
    int32_t event_id,
    void *event_data
)
{
    (void)handler_args;
    (void)base;

    esp_mqtt_event_handle_t event =
        (esp_mqtt_event_handle_t)event_data;

    switch (
        (esp_mqtt_event_id_t)event_id
    ) {
        case MQTT_EVENT_CONNECTED:
            s_mqtt_connected = true;
            s_echo_subscribed = false;

            ESP_LOGI(
                TAG,
                "MQTT connected"
            );

            esp_mqtt_client_subscribe(
                s_client,
                s_echo_topic,
                OCC_MQTT_QOS
            );

            break;

        case MQTT_EVENT_SUBSCRIBED:
            s_echo_subscribed = true;

            ESP_LOGI(
                TAG,
                "echo subscription active topic=%s",
                s_echo_topic
            );

            break;

        case MQTT_EVENT_DISCONNECTED:
            s_mqtt_connected = false;
            s_echo_subscribed = false;

            reset_echo_reassembly();

            ESP_LOGW(
                TAG,
                "MQTT disconnected; automatic reconnect pending"
            );

            break;

        case MQTT_EVENT_DATA:
            handle_echo_fragment(event);
            break;

        case MQTT_EVENT_ERROR:
            ESP_LOGW(
                TAG,
                "MQTT transport error"
            );
            break;

        default:
            break;
    }
}


static bool build_topics(void)
{
    int telemetry_len =
        snprintf(
            s_telemetry_topic,
            sizeof(s_telemetry_topic),
            "fair/v1/%s/telemetry",
            CONFIG_OCC_VEHICLE_ID
        );

    int echo_len =
        snprintf(
            s_echo_topic,
            sizeof(s_echo_topic),
            "fair/v1/%s/echo",
            CONFIG_OCC_VEHICLE_ID
        );

    return
        telemetry_len > 0 &&
        telemetry_len <
            (int)sizeof(s_telemetry_topic) &&
        echo_len > 0 &&
        echo_len <
            (int)sizeof(s_echo_topic);
}


static int build_payload(
    char *buffer,
    size_t buffer_size,
    uint32_t seq
)
{
    const int64_t t_source_us =
        esp_timer_get_time();

    return snprintf(
        buffer,
        buffer_size,
        "{"
        "\"schema_ver\":\"runtime-1.0\","
        "\"serialNumber\":\"%s\","
        "\"seq\":%" PRIu32 ","
        "\"t_source_us\":%" PRId64 ","
        "\"speed\":0.0,"
        "\"pos_x\":0.0,"
        "\"pos_y\":0.0,"
        "\"heading\":0.0,"
        "\"battery_pct\":100.0,"
        "\"state\":\"IDLE\""
        "}",
        CONFIG_OCC_VEHICLE_ID,
        seq,
        t_source_us
    );
}


void app_main(void)
{
    ESP_LOGI(
        TAG,
        "OCC MQTT operational runtime starting"
    );

    ESP_LOGI(
        TAG,
        "vehicle=%s broker=%s period_ms=%d",
        CONFIG_OCC_VEHICLE_ID,
        CONFIG_OCC_MQTT_BROKER_URI,
        CONFIG_OCC_RUNTIME_PERIOD_MS
    );

    if (
        strlen(CONFIG_OCC_WIFI_SSID) == 0U
    ) {
        ESP_LOGE(
            TAG,
            "Wi-Fi is not configured"
        );

        return;
    }

    if (
        strlen(CONFIG_OCC_MQTT_BROKER_URI) == 0U ||
        strlen(CONFIG_OCC_VEHICLE_ID) == 0U
    ) {
        ESP_LOGE(
            TAG,
            "broker URI / vehicle identity missing"
        );

        return;
    }

    if (!build_topics()) {
        ESP_LOGE(
            TAG,
            "MQTT topic construction failed"
        );

        return;
    }

    esp_err_t err =
        fair_mqtt_network_connect(
            CONFIG_OCC_WIFI_SSID,
            CONFIG_OCC_WIFI_PASSWORD,
            pdMS_TO_TICKS(30000)
        );

    if (err != ESP_OK) {
        ESP_LOGE(
            TAG,
            "initial Wi-Fi connection failed: %s",
            esp_err_to_name(err)
        );

        ESP_LOGW(
            TAG,
            "restarting in 5 seconds"
        );

        vTaskDelay(
            pdMS_TO_TICKS(5000)
        );

        esp_restart();
        return;
    }

    esp_mqtt_client_config_t mqtt_config = {
        .broker.address.uri =
            CONFIG_OCC_MQTT_BROKER_URI,
    };

    s_client =
        esp_mqtt_client_init(
            &mqtt_config
        );

    if (s_client == NULL) {
        ESP_LOGE(
            TAG,
            "MQTT client initialization failed"
        );

        return;
    }

    ESP_ERROR_CHECK(
        esp_mqtt_client_register_event(
            s_client,
            ESP_EVENT_ANY_ID,
            mqtt_event_handler,
            NULL
        )
    );

    ESP_ERROR_CHECK(
        esp_mqtt_client_start(
            s_client
        )
    );

    uint32_t seq = 0U;

    TickType_t last_wake =
        xTaskGetTickCount();

    const TickType_t period_ticks =
        pdMS_TO_TICKS(
            CONFIG_OCC_RUNTIME_PERIOD_MS
        );

    uint32_t waiting_log_counter = 0U;

    while (true) {
        if (
            s_mqtt_connected &&
            s_echo_subscribed
        ) {
            char payload[
                PAYLOAD_BUFFER_BYTES
            ];

            const int payload_len =
                build_payload(
                    payload,
                    sizeof(payload),
                    seq
                );

            if (
                payload_len <= 0 ||
                payload_len >=
                    (int)sizeof(payload)
            ) {
                ESP_LOGE(
                    TAG,
                    "payload construction failed"
                );
            } else {
                const int rc =
                    esp_mqtt_client_enqueue(
                        s_client,
                        s_telemetry_topic,
                        payload,
                        payload_len,
                        OCC_MQTT_QOS,
                        0,
                        false
                    );

                if (rc >= 0) {
                    if (
                        seq % 100U == 0U
                    ) {
                        ESP_LOGI(
                            TAG,
                            "telemetry seq=%" PRIu32
                            " mqtt_id=%d",
                            seq,
                            rc
                        );
                    }
                } else {
                    ESP_LOGW(
                        TAG,
                        "telemetry enqueue failed seq=%"
                        PRIu32,
                        seq
                    );
                }

                /*
                 * Operational sequence is continuous.
                 * It is intentionally NOT limited to 0..599.
                 */
                ++seq;
            }

            waiting_log_counter = 0U;
        } else {
            ++waiting_log_counter;

            if (
                waiting_log_counter %
                    50U == 0U
            ) {
                ESP_LOGI(
                    TAG,
                    "waiting for MQTT + echo subscription"
                );
            }
        }

        vTaskDelayUntil(
            &last_wake,
            period_ticks
        );
    }
}
