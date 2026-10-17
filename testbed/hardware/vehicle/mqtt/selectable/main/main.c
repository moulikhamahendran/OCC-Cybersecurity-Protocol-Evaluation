#include "occ_parallel_demo.h"
#include "esp_heap_caps.h"
#include "opcua_c0_runtime.h"
#include "protocol_manager.h"
#include "dds_c0_runtime.h" /* OCC_DDS_C0_STREAM_V1 */
#include "opcua_c0_adapter.h"

#include "protocol_selection.h"
#include "occ_management.h"
#include "esp_wifi.h"
#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "cJSON.h"

#include "esp_err.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif_sntp.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "nvs_flash.h"
#include "driver/gpio.h"
#include "mqtt_client.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "runtime_wifi.h"
#include "runtime_mqtt_config.h"
#include "runtime_endpoint_config.h"
#include "runtime_known_wifi.h"
#include "vehicle_state.h"


extern const char fair_v1_c2_ca_crt_start[]
    asm("_binary_fair_v1_c2_ca_crt_start");

#define OCC_MQTT_QOS 1
#define TOPIC_BUFFER_BYTES 128
#define PAYLOAD_BUFFER_BYTES 384
#define ECHO_BUFFER_BYTES 192
#define CONTROL_BUFFER_BYTES 192
#define STATUS_BUFFER_BYTES 192
#define BROKER_URI_BUFFER_BYTES 192

static const char *TAG = "OCC_MQTT_RUNTIME";


#define OCC_RECOVERY_BUTTON_GPIO GPIO_NUM_0
#define OCC_RECOVERY_HOLD_MS 3000
#define OCC_RECOVERY_POLL_MS 50

static void local_recovery_button_task(void *arg)
{
    (void)arg;

    const gpio_config_t io_conf = {
        .pin_bit_mask = 1ULL << OCC_RECOVERY_BUTTON_GPIO,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };

    esp_err_t err = gpio_config(&io_conf);

    if (err != ESP_OK) {
        ESP_LOGE(
            TAG,
            "Local recovery button GPIO init failed: %s",
            esp_err_to_name(err)
        );
        vTaskDelete(NULL);
        return;
    }

    ESP_LOGI(
        TAG,
        "Local Wi-Fi recovery ready: hold BOOT for 3 seconds"
    );

    uint32_t held_ms = 0U;
    bool reprovision_requested = false;

    while (true) {
        const int level =
            gpio_get_level(OCC_RECOVERY_BUTTON_GPIO);

        if (level == 0) {
            if (!reprovision_requested) {
                held_ms += OCC_RECOVERY_POLL_MS;

                if (held_ms >= OCC_RECOVERY_HOLD_MS) {
                    err =
                        occ_known_wifi_request_reprovision();

                    if (err == ESP_OK) {
                        reprovision_requested = true;

                        ESP_LOGW(
                            TAG,
                            "BOOT hold accepted; Wi-Fi reprovisioning scheduled"
                        );

                        ESP_LOGW(
                            TAG,
                            "Release BOOT button to restart into provisioning mode"
                        );
                    } else {
                        ESP_LOGE(
                            TAG,
                            "Local Wi-Fi reprovision request failed: %s",
                            esp_err_to_name(err)
                        );

                        held_ms = 0U;
                    }
                }
            }
        } else {
            if (reprovision_requested) {
                ESP_LOGW(
                    TAG,
                    "BOOT released; restarting into Wi-Fi provisioning mode"
                );

                vTaskDelay(pdMS_TO_TICKS(200));
                esp_restart();
            }

            held_ms = 0U;
        }

        vTaskDelay(
            pdMS_TO_TICKS(OCC_RECOVERY_POLL_MS)
        );
    }
}


static esp_mqtt_client_handle_t s_client = NULL;

static occ_mqtt_credentials_t s_mqtt_credentials;
static occ_mqtt_profile_t s_mqtt_profile;

static volatile bool s_mqtt_connected = false;
static volatile bool s_echo_subscribed = false;
static volatile bool s_control_subscribed = false;

static int s_echo_sub_msg_id = -1;
static int s_control_sub_msg_id = -1;

static char s_vehicle_id[OCC_VEHICLE_ID_MAX_LEN];

static char s_occ_host[OCC_ENDPOINT_HOST_MAX_LEN];
static char s_broker_uri[BROKER_URI_BUFFER_BYTES];

static char s_telemetry_topic[TOPIC_BUFFER_BYTES];
static char s_echo_topic[TOPIC_BUFFER_BYTES];
static char s_control_topic[TOPIC_BUFFER_BYTES];
static char s_status_topic[TOPIC_BUFFER_BYTES];

static char s_echo_buffer[ECHO_BUFFER_BYTES];
static size_t s_echo_expected_len = 0U;
static size_t s_echo_received_len = 0U;
static bool s_echo_active = false;

static uint64_t s_echo_count = 0U;

static char s_control_buffer[CONTROL_BUFFER_BYTES];
static size_t s_control_expected_len = 0U;
static size_t s_control_received_len = 0U;
static bool s_control_active = false;

static volatile bool s_profile_change_pending = false;
static volatile occ_mqtt_profile_t s_requested_profile =
    OCC_MQTT_PROFILE_C2;

static volatile bool s_vehicle_id_change_pending = false;
static char s_requested_vehicle_id[OCC_VEHICLE_ID_MAX_LEN];

static volatile bool s_credentials_clear_pending = false;

static volatile bool s_endpoint_change_pending = false;
static volatile bool s_wifi_reprovision_pending = false;
static char s_requested_occ_host[OCC_ENDPOINT_HOST_MAX_LEN];

static bool s_runtime_status_published = false;


static void reset_echo_reassembly(void)
{
    s_echo_expected_len = 0U;
    s_echo_received_len = 0U;
    s_echo_active = false;
    s_echo_buffer[0] = '\0';
}


static void reset_control_reassembly(void)
{
    s_control_expected_len = 0U;
    s_control_received_len = 0U;
    s_control_active = false;
    s_control_buffer[0] = '\0';
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
            s_vehicle_id
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
        if (
            !topic_matches(
                event->topic,
                event->topic_len,
                s_echo_topic
            )
        ) {
            return;
        }

        reset_echo_reassembly();

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


static bool vehicle_id_is_valid(
    const char *vehicle_id
)
{
    if (
        vehicle_id == NULL ||
        vehicle_id[0] == '\0'
    ) {
        return false;
    }

    const size_t len = strlen(vehicle_id);

    if (len >= OCC_VEHICLE_ID_MAX_LEN) {
        return false;
    }

    for (size_t i = 0U; i < len; ++i) {
        const char c = vehicle_id[i];

        const bool allowed =
            (c >= 'A' && c <= 'Z') ||
            (c >= 'a' && c <= 'z') ||
            (c >= '0' && c <= '9') ||
            c == '-' ||
            c == '_';

        if (!allowed) {
            return false;
        }
    }

    return true;
}


static void handle_complete_control(void)
{
    cJSON *root =
        cJSON_ParseWithLength(
            s_control_buffer,
            s_control_received_len
        );

    if (root == NULL) {
        ESP_LOGW(
            TAG,
            "invalid control JSON"
        );

        return;
    }

    const cJSON *command =
        cJSON_GetObjectItemCaseSensitive(
            root,
            "command"
        );

    if (
        !cJSON_IsString(command) ||
        command->valuestring == NULL
    ) {
        ESP_LOGW(
            TAG,
            "control command missing"
        );

        cJSON_Delete(root);
        return;
    }

    if (
        strcmp(
            command->valuestring,
            "set_profile"
        ) == 0
    ) {
        const cJSON *profile =
            cJSON_GetObjectItemCaseSensitive(
                root,
                "profile"
            );

        if (
            !cJSON_IsString(profile) ||
            profile->valuestring == NULL
        ) {
            ESP_LOGW(
                TAG,
                "requested MQTT profile missing"
            );

            cJSON_Delete(root);
            return;
        }

        occ_mqtt_profile_t requested_profile;

        esp_err_t err =
            occ_mqtt_profile_from_string(
                profile->valuestring,
                &requested_profile
            );

        if (err != ESP_OK) {
            ESP_LOGW(
                TAG,
                "invalid requested MQTT profile"
            );

            cJSON_Delete(root);
            return;
        }

        if (
            s_wifi_reprovision_pending ||
            s_endpoint_change_pending ||
            s_profile_change_pending ||
            s_vehicle_id_change_pending ||
            s_credentials_clear_pending
        ) {
            ESP_LOGW(
                TAG,
                "runtime configuration change already pending"
            );

            cJSON_Delete(root);
            return;
        }

        s_requested_profile = requested_profile;
        s_profile_change_pending = true;

        ESP_LOGI(
            TAG,
            "profile change requested current=%s requested=%s",
            occ_mqtt_profile_to_string(
                s_mqtt_profile
            ),
            occ_mqtt_profile_to_string(
                requested_profile
            )
        );

        cJSON_Delete(root);
        return;
    }

    if (
        strcmp(
            command->valuestring,
            "set_vehicle_id"
        ) == 0
    ) {
        const cJSON *vehicle_id =
            cJSON_GetObjectItemCaseSensitive(
                root,
                "vehicle_id"
            );

        if (
            !cJSON_IsString(vehicle_id) ||
            vehicle_id->valuestring == NULL ||
            !vehicle_id_is_valid(
                vehicle_id->valuestring
            )
        ) {
            ESP_LOGW(
                TAG,
                "invalid requested vehicle identity"
            );

            cJSON_Delete(root);
            return;
        }

        if (
            s_wifi_reprovision_pending ||
            s_endpoint_change_pending ||
            s_profile_change_pending ||
            s_vehicle_id_change_pending ||
            s_credentials_clear_pending
        ) {
            ESP_LOGW(
                TAG,
                "runtime configuration change already pending"
            );

            cJSON_Delete(root);
            return;
        }

        const int written =
            snprintf(
                s_requested_vehicle_id,
                sizeof(s_requested_vehicle_id),
                "%s",
                vehicle_id->valuestring
            );

        if (
            written <= 0 ||
            written >=
                (int)sizeof(s_requested_vehicle_id)
        ) {
            ESP_LOGW(
                TAG,
                "requested vehicle identity too long"
            );

            cJSON_Delete(root);
            return;
        }

        s_vehicle_id_change_pending = true;

        ESP_LOGI(
            TAG,
            "vehicle identity change requested current=%s requested=%s",
            s_vehicle_id,
            s_requested_vehicle_id
        );

        cJSON_Delete(root);
        return;
    }

    if (
        strcmp(
            command->valuestring,
            "clear_mqtt_credentials"
        ) == 0
    ) {
        if (s_mqtt_profile != OCC_MQTT_PROFILE_C2) {
            ESP_LOGW(
                TAG,
                "MQTT credential reset rejected: C2 required"
            );

            cJSON_Delete(root);
            return;
        }

        if (
            s_wifi_reprovision_pending ||
            s_endpoint_change_pending ||
            s_profile_change_pending ||
            s_vehicle_id_change_pending ||
            s_credentials_clear_pending
        ) {
            ESP_LOGW(
                TAG,
                "runtime configuration change already pending"
            );

            cJSON_Delete(root);
            return;
        }

        s_credentials_clear_pending = true;

        ESP_LOGI(
            TAG,
            "MQTT credential reprovisioning requested"
        );

        cJSON_Delete(root);
        return;
    }

    if (
        strcmp(
            command->valuestring,
            "reprovision_wifi"
        ) == 0
    ) {
        /*
         * Wi-Fi administration is deliberately restricted
         * to C2 because C0/C1 do not provide encrypted
         * control transport.
         */
        if (s_mqtt_profile != OCC_MQTT_PROFILE_C2) {
            ESP_LOGW(
                TAG,
                "Wi-Fi reprovision rejected: C2 required"
            );

            cJSON_Delete(root);
            return;
        }

        if (
            s_wifi_reprovision_pending ||
            s_endpoint_change_pending ||
            s_profile_change_pending ||
            s_vehicle_id_change_pending ||
            s_credentials_clear_pending
        ) {
            ESP_LOGW(
                TAG,
                "runtime configuration change already pending"
            );

            cJSON_Delete(root);
            return;
        }

        esp_err_t wifi_admin_err =
            occ_known_wifi_request_reprovision();

        if (wifi_admin_err != ESP_OK) {
            ESP_LOGE(
                TAG,
                "failed to persist Wi-Fi reprovision request: %s",
                esp_err_to_name(
                    wifi_admin_err
                )
            );

            cJSON_Delete(root);
            return;
        }

        s_wifi_reprovision_pending = true;

        ESP_LOGI(
            TAG,
            "Wi-Fi reprovisioning scheduled"
        );

        cJSON_Delete(root);
        return;
    }

    if (
        strcmp(
            command->valuestring,
            "set_occ_host"
        ) == 0
    ) {
        /*
         * Endpoint mutation is intentionally accepted only
         * through authenticated + TLS-protected C2 control.
         */
        if (s_mqtt_profile != OCC_MQTT_PROFILE_C2) {
            ESP_LOGW(
                TAG,
                "OCC endpoint change rejected: C2 required"
            );

            cJSON_Delete(root);
            return;
        }

        const cJSON *host =
            cJSON_GetObjectItemCaseSensitive(
                root,
                "host"
            );

        if (
            !cJSON_IsString(host) ||
            host->valuestring == NULL ||
            !occ_endpoint_host_is_valid(
                host->valuestring
            )
        ) {
            ESP_LOGW(
                TAG,
                "invalid requested OCC host"
            );

            cJSON_Delete(root);
            return;
        }

        if (
            s_wifi_reprovision_pending ||
            s_endpoint_change_pending ||
            s_profile_change_pending ||
            s_vehicle_id_change_pending ||
            s_credentials_clear_pending
        ) {
            ESP_LOGW(
                TAG,
                "runtime configuration change already pending"
            );

            cJSON_Delete(root);
            return;
        }

        const int written =
            snprintf(
                s_requested_occ_host,
                sizeof(s_requested_occ_host),
                "%s",
                host->valuestring
            );

        if (
            written <= 0 ||
            written >=
                (int)sizeof(s_requested_occ_host)
        ) {
            ESP_LOGW(
                TAG,
                "requested OCC host too long"
            );

            cJSON_Delete(root);
            return;
        }

        s_endpoint_change_pending = true;

        ESP_LOGI(
            TAG,
            "OCC endpoint change requested"
        );

        cJSON_Delete(root);
        return;
    }

    ESP_LOGW(
        TAG,
        "unsupported control command"
    );

    cJSON_Delete(root);
}

static void handle_control_fragment(
    esp_mqtt_event_handle_t event
)
{
    if (event == NULL) {
        return;
    }

    if (event->current_data_offset == 0) {
        if (
            !topic_matches(
                event->topic,
                event->topic_len,
                s_control_topic
            )
        ) {
            return;
        }

        reset_control_reassembly();

        if (
            event->total_data_len <= 0 ||
            event->total_data_len >=
                (int)sizeof(s_control_buffer)
        ) {
            ESP_LOGW(
                TAG,
                "control message too large total=%d",
                event->total_data_len
            );

            return;
        }

        s_control_expected_len =
            (size_t)event->total_data_len;

        s_control_active = true;
    }

    if (!s_control_active) {
        return;
    }

    if (
        event->current_data_offset < 0 ||
        event->data_len < 0
    ) {
        reset_control_reassembly();
        return;
    }

    const size_t offset =
        (size_t)event->current_data_offset;

    const size_t fragment_len =
        (size_t)event->data_len;

    if (
        offset != s_control_received_len ||
        offset + fragment_len >
            s_control_expected_len ||
        offset + fragment_len >=
            sizeof(s_control_buffer)
    ) {
        ESP_LOGW(
            TAG,
            "invalid control fragment"
        );

        reset_control_reassembly();
        return;
    }

    memcpy(
        s_control_buffer + offset,
        event->data,
        fragment_len
    );

    s_control_received_len += fragment_len;

    if (
        s_control_received_len !=
        s_control_expected_len
    ) {
        return;
    }

    s_control_buffer[s_control_received_len] =
        '\0';

    handle_complete_control();

    reset_control_reassembly();
}


static void publish_profile_status(
    const char *result,
    occ_mqtt_profile_t requested_profile
)
{
    char status[STATUS_BUFFER_BYTES];

    const int status_len =
        snprintf(
            status,
            sizeof(status),
            "{"
            "\"vehicle_id\":\"%s\","
            "\"active_profile\":\"%s\","
            "\"requested_profile\":\"%s\","
            "\"result\":\"%s\""
            "}",
            s_vehicle_id,
            occ_mqtt_profile_to_string(
                s_mqtt_profile
            ),
            occ_mqtt_profile_to_string(
                requested_profile
            ),
            result
        );

    if (
        status_len <= 0 ||
        status_len >=
            (int)sizeof(status)
    ) {
        ESP_LOGW(
            TAG,
            "status payload construction failed"
        );

        return;
    }

    const int msg_id =
        esp_mqtt_client_publish(
            s_client,
            s_status_topic,
            status,
            status_len,
            OCC_MQTT_QOS,
            0
        );

    if (msg_id < 0) {
        ESP_LOGW(
            TAG,
            "profile status publish failed"
        );
    }
}



static void publish_vehicle_id_status(
    const char *result,
    const char *requested_vehicle_id
)
{
    char status[STATUS_BUFFER_BYTES];

    const int status_len =
        snprintf(
            status,
            sizeof(status),
            "{"
            "\"vehicle_id\":\"%s\","
            "\"active_profile\":\"%s\","
            "\"requested_vehicle_id\":\"%s\","
            "\"result\":\"%s\""
            "}",
            s_vehicle_id,
            occ_mqtt_profile_to_string(
                s_mqtt_profile
            ),
            requested_vehicle_id,
            result
        );

    if (
        status_len <= 0 ||
        status_len >=
            (int)sizeof(status)
    ) {
        ESP_LOGW(
            TAG,
            "vehicle identity status construction failed"
        );

        return;
    }

    const int msg_id =
        esp_mqtt_client_publish(
            s_client,
            s_status_topic,
            status,
            status_len,
            OCC_MQTT_QOS,
            0
        );

    if (msg_id < 0) {
        ESP_LOGW(
            TAG,
            "vehicle identity status publish failed"
        );
    }
}


static void publish_credentials_status(
    const char *result
)
{
    char status[STATUS_BUFFER_BYTES];

    const int status_len =
        snprintf(
            status,
            sizeof(status),
            "{"
            "\"vehicle_id\":\"%s\","
            "\"active_profile\":\"%s\","
            "\"result\":\"%s\""
            "}",
            s_vehicle_id,
            occ_mqtt_profile_to_string(
                s_mqtt_profile
            ),
            result
        );

    if (
        status_len <= 0 ||
        status_len >=
            (int)sizeof(status)
    ) {
        ESP_LOGW(
            TAG,
            "credential status construction failed"
        );

        return;
    }

    const int msg_id =
        esp_mqtt_client_publish(
            s_client,
            s_status_topic,
            status,
            status_len,
            OCC_MQTT_QOS,
            0
        );

    if (msg_id < 0) {
        ESP_LOGW(
            TAG,
            "credential status publish failed"
        );
    }
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
            s_control_subscribed = false;

            ESP_LOGI(
                TAG,
                "MQTT connected"
            );

            s_echo_sub_msg_id =
                esp_mqtt_client_subscribe(
                    s_client,
                    s_echo_topic,
                    OCC_MQTT_QOS
                );

            s_control_sub_msg_id =
                esp_mqtt_client_subscribe(
                    s_client,
                    s_control_topic,
                    OCC_MQTT_QOS
                );

            if (
                s_echo_sub_msg_id < 0 ||
                s_control_sub_msg_id < 0
            ) {
                ESP_LOGE(
                    TAG,
                    "MQTT subscription request failed"
                );
            }

            break;

        case MQTT_EVENT_SUBSCRIBED:
            if (
                event->msg_id ==
                s_echo_sub_msg_id
            ) {
                s_echo_subscribed = true;

                ESP_LOGI(
                    TAG,
                    "echo subscription active topic=%s",
                    s_echo_topic
                );
            }

            if (
                event->msg_id ==
                s_control_sub_msg_id
            ) {
                s_control_subscribed = true;

                ESP_LOGI(
                    TAG,
                    "control subscription active topic=%s",
                    s_control_topic
                );
            }

            break;

        case MQTT_EVENT_DISCONNECTED:
            s_mqtt_connected = false;
            s_echo_subscribed = false;
            s_control_subscribed = false;
            s_echo_sub_msg_id = -1;
            s_control_sub_msg_id = -1;
            s_runtime_status_published = false;

            reset_echo_reassembly();
            reset_control_reassembly();

            ESP_LOGW(
                TAG,
                "MQTT disconnected; automatic reconnect pending"
            );

            break;

        case MQTT_EVENT_DATA:
            handle_echo_fragment(event);
            handle_control_fragment(event);
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
    const char *profile =
        occ_mqtt_profile_to_string(
            s_mqtt_profile
        );

    if (strcmp(profile, "UNKNOWN") == 0) {
        return false;
    }

    int telemetry_len =
        snprintf(
            s_telemetry_topic,
            sizeof(s_telemetry_topic),
            "occ/runtime/%s/%s/telemetry",
            profile,
            s_vehicle_id
        );

    int echo_len =
        snprintf(
            s_echo_topic,
            sizeof(s_echo_topic),
            "occ/runtime/%s/%s/echo",
            profile,
            s_vehicle_id
        );

    int control_len =
        snprintf(
            s_control_topic,
            sizeof(s_control_topic),
            "occ/runtime/%s/%s/control",
            profile,
            s_vehicle_id
        );

    int status_len =
        snprintf(
            s_status_topic,
            sizeof(s_status_topic),
            "occ/runtime/%s/%s/status",
            profile,
            s_vehicle_id
        );

    return
        telemetry_len > 0 &&
        telemetry_len <
            (int)sizeof(s_telemetry_topic) &&
        echo_len > 0 &&
        echo_len <
            (int)sizeof(s_echo_topic) &&
        control_len > 0 &&
        control_len <
            (int)sizeof(s_control_topic) &&
        status_len > 0 &&
        status_len <
            (int)sizeof(s_status_topic);
}


static int build_payload(
    char *buffer,
    size_t buffer_size,
    uint32_t *seq_out
)
{
    if (
        buffer == NULL ||
        seq_out == NULL
    ) {
        return -1;
    }

    vehicle_state_t vehicle;

    if (!vehicle_state_get(&vehicle)) {
        ESP_LOGE(
            TAG,
            "vehicle state unavailable"
        );

        return -1;
    }

    *seq_out = vehicle.seq;

    return snprintf(
        buffer,
        buffer_size,
        "{"
        "\"schema_ver\":\"runtime-1.0\","
        "\"serialNumber\":\"%s\","
        "\"seq\":%" PRIu32 ","
        "\"t_source_us\":%" PRId64 ","
        "\"speed\":%.3f,"
        "\"pos_x\":%.3f,"
        "\"pos_y\":%.3f,"
        "\"heading\":%.3f,"
        "\"battery_pct\":%.3f,"
        "\"state\":\"%s\""
        "}",
        s_vehicle_id,
        vehicle.seq,
        vehicle.t_source_us,
        (double)vehicle.speed,
        (double)vehicle.pos_x,
        (double)vehicle.pos_y,
        (double)vehicle.heading,
        (double)vehicle.battery_pct,
        vehicle.state
    );
}

/* OCC_PRECRYPTO_PROBE_V1 (diagnostic only) */
#include "lwip/sockets.h"
#include "lwip/inet.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <stdio.h>
#include <errno.h>
#include <fcntl.h>
#include <string.h>


/* Runs BEFORE any OPC UA certificate/encryption initialization.
 * Do not use this temporary diagnostic as operational firmware. */
static void occ_precrypto_probe_v1(void) {
    printf("OCC_PRECRYPTO_IDLE_BEGIN wait_ms=15000 no_opcua_client=1\n"); fflush(stdout);
    vTaskDelay(pdMS_TO_TICKS(15000));
    printf("OCC_PRECRYPTO_IDLE_PASS no_opcua_client=1\n"); fflush(stdout);
    struct sockaddr_in a;
    memset(&a, 0, sizeof(a));
    a.sin_family = AF_INET;
    a.sin_port = htons(14841);
    if(inet_pton(AF_INET, "192.168.1.115", &a.sin_addr) != 1) {
        printf("OCC_PRECRYPTO_SETUP_FAIL\n"); fflush(stdout);
        for(;;) vTaskDelay(pdMS_TO_TICKS(10000));
    }
    printf("OCC_PRECRYPTO_TCP_BEGIN endpoint=192.168.1.115:14841 attempts=12 no_opcua_client=1\n"); fflush(stdout);
    unsigned passed=0, failed=0;
    for(unsigned i=1; i<=12; ++i) {
        int fd=socket(AF_INET, SOCK_STREAM, IPPROTO_IP);
        int e=0, good=0;
        if(fd<0) e=errno;
        else {
            int fl=fcntl(fd,F_GETFL,0);
            if(fl<0 || fcntl(fd,F_SETFL,fl|O_NONBLOCK)<0) e=errno;
            else {
                int r=connect(fd,(const struct sockaddr*)&a,sizeof(a));
                if(r==0) good=1;
                else if(errno==EINPROGRESS) {
                    fd_set w; FD_ZERO(&w); FD_SET(fd,&w);
                    struct timeval t={.tv_sec=2,.tv_usec=0};
                    int sr=select(fd+1,NULL,&w,NULL,&t);
                    if(sr>0) {
                        socklen_t n=sizeof(e);
                        if(getsockopt(fd,SOL_SOCKET,SO_ERROR,&e,&n)==0 && e==0) good=1;
                        else if(e==0) e=errno;
                    } else e=sr==0?ETIMEDOUT:errno;
                } else e=errno;
            }
            close(fd);
        }
        if(good) ++passed; else ++failed;
        printf("OCC_PRECRYPTO_TCP_ATTEMPT %u/12 connected=%d errno=%d\n",i,good,e); fflush(stdout);
        vTaskDelay(pdMS_TO_TICKS(750));
    }
    printf("OCC_PRECRYPTO_TCP_DONE passed=%u failed=%u\n",passed,failed); fflush(stdout);
    printf("OCC_CRYPTO_BOUNDARY_DIAG_V1 PRECRYPTO_TCP_FINISHED proceeding_to_c1_init=1\n"); fflush(stdout);
    return;
}



extern esp_err_t occ_opcua_provision_boot(void);
extern esp_err_t occ_unified_select_boot(void);


/* OCC_PARALLEL_SECURE_PROFILES_V2 */
#if OCC_PARALLEL_DEMO_ENABLED
static occ_security_t s_parallel_security = OCC_SECURITY_C0;
static bool s_parallel_opcua_provisioned = true;

static void occ_parallel_opcua_task(void *arg)
{
    (void)arg;
    vTaskDelay(pdMS_TO_TICKS(5000));
    if (!s_parallel_opcua_provisioned) {
        ESP_LOGE(TAG,"PARALLEL secure OPC UA blocked: provisioning unavailable");
        vTaskDelete(NULL);
        return;
    }
    char url[256];
    int port = 14840 + (int)s_parallel_security;
    int n = snprintf(url,sizeof(url),"opc.tcp://%s:%d",s_occ_host,port);
    if (n > 0 && n < (int)sizeof(url)) {
        ESP_LOGI(TAG,"PARALLEL starting OPC UA C%d",(int)s_parallel_security);
        esp_err_t rc = occ_opcua_run(s_vehicle_id,url,s_parallel_security);
        ESP_LOGE(TAG,"PARALLEL OPC UA returned %s",esp_err_to_name(rc));
    }
    vTaskDelete(NULL);
}
static void occ_parallel_dds_task(void *arg)
{
    (void)arg;
    vTaskDelay(pdMS_TO_TICKS(7000));
    ESP_LOGI(TAG,"PARALLEL starting DDS C%d",(int)s_parallel_security);
    esp_err_t rc = occ_dds_run(s_vehicle_id,s_occ_host,(int)s_parallel_security);
    ESP_LOGE(TAG,"PARALLEL DDS returned %s",esp_err_to_name(rc));
    vTaskDelete(NULL);
}
static void occ_parallel_demo_start(void)
{
    size_t free_mem=heap_caps_get_free_size(MALLOC_CAP_8BIT);
    size_t largest=heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);
    ESP_LOGI(TAG,"PARALLEL heap=%lu largest=%lu",
        (unsigned long)free_mem,(unsigned long)largest);
    if (free_mem<100000U || largest<18000U) {
        ESP_LOGE(TAG,"PARALLEL blocked: insufficient memory");
        return;
    }
    BaseType_t a=xTaskCreate(occ_parallel_opcua_task,
        "parallel_opcua",14336,NULL,4,NULL);
    BaseType_t b=pdFAIL;
    if(a==pdPASS)
        b=xTaskCreate(occ_parallel_dds_task,
            "parallel_dds",10240,NULL,4,NULL);
    ESP_LOGI(TAG,"PARALLEL tasks OPCUA=%d DDS=%d",(int)a,(int)b);
}
#endif

void app_main(void)
{
    /* OCC_UNIFIED_OPCUA_REAL_LINK_TEST_V2
     * Reference the actual client startup function.
     * Do not create or connect an OPC UA client.
     */
    ESP_LOGI(
        TAG,
        "OPC UA C0 client link address=%p",
        (void *)occ_opcua_c0_start
    );

    ESP_LOGI(
        TAG,
        "OCC MQTT selectable operational runtime starting"
    );

    /* Initialize persistent sequence storage before starting the state task.
     * Do not automatically erase NVS: that could reset the replay counter. */
    esp_err_t err = nvs_flash_init();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "NVS initialization failed (no erase): %s",
                 esp_err_to_name(err));
        return;
    }

    /* Local USB protocol/profile selection. */
    err = occ_unified_select_boot();
    if (err != ESP_OK) {
        ESP_LOGE(TAG,
                 "Unified selection service failed: %s",
                 esp_err_to_name(err));
        return;
    }

    /*
     * OPC UA C1/C2 only:
     * optional local USB credential provisioning.
     * MQTT and OPC UA C0 never enter this provisioning window.
     */
    {
        occ_protocol_selection_t boot_selection = {0};

        if (occ_protocol_selection_load(&boot_selection) == ESP_OK &&
            (
                boot_selection.protocol == OCC_PROTOCOL_OPCUA
#if OCC_PARALLEL_DEMO_ENABLED
                || boot_selection.protocol == OCC_PROTOCOL_MQTT
#endif
            ) &&
            (boot_selection.security == OCC_SECURITY_C1 ||
             boot_selection.security == OCC_SECURITY_C2)) {

            esp_err_t provision_rc = occ_opcua_provision_boot();
#if OCC_PARALLEL_DEMO_ENABLED
            if (boot_selection.protocol == OCC_PROTOCOL_MQTT)
                s_parallel_opcua_provisioned = (provision_rc == ESP_OK);
#endif
            if (provision_rc != ESP_OK) {
                ESP_LOGW(TAG,
                    "Dedicated OPC UA provisioning not completed: %s",
                    esp_err_to_name(provision_rc));
            }
        }
    }



    err =
        vehicle_state_start(
            CONFIG_OCC_RUNTIME_PERIOD_MS
        );

    if (err != ESP_OK) {
        ESP_LOGE(
            TAG,
            "vehicle state engine failed to start: %s",
            esp_err_to_name(err)
        );

        return;
    }

    ESP_LOGI(
        TAG,
        "vehicle core active before network startup"
    );

    BaseType_t recovery_task_created =
        xTaskCreate(
            local_recovery_button_task,
            "occ_wifi_recovery",
            3072,
            NULL,
            5,
            NULL
        );

    if (recovery_task_created != pdPASS) {
        ESP_LOGE(
            TAG,
            "Failed to start local Wi-Fi recovery task"
        );
    }

    err =
        occ_runtime_wifi_connect_or_provision();

    if (err != ESP_OK) {
        ESP_LOGE(
            TAG,
            "Wi-Fi provisioning/connect failed: %s; vehicle core remains active",
            esp_err_to_name(err)
        );

        return;
    }

    err =
        occ_vehicle_id_load(
            s_vehicle_id,
            sizeof(s_vehicle_id)
        );

    if (err != ESP_OK) {
        ESP_LOGW(
            TAG,
            "No saved vehicle identity; using default=%s",
            CONFIG_OCC_VEHICLE_ID
        );

        const int vehicle_id_len =
            snprintf(
                s_vehicle_id,
                sizeof(s_vehicle_id),
                "%s",
                CONFIG_OCC_VEHICLE_ID
            );

        if (
            vehicle_id_len <= 0 ||
            vehicle_id_len >=
                (int)sizeof(s_vehicle_id)
        ) {
            ESP_LOGE(
                TAG,
                "Default vehicle identity is invalid"
            );

            return;
        }

        err =
            occ_vehicle_id_save(
                s_vehicle_id
            );

        if (err != ESP_OK) {
            ESP_LOGE(
                TAG,
                "Failed to save default vehicle identity: %s",
                esp_err_to_name(err)
            );

            return;
        }
    }

    if (s_vehicle_id[0] == '\0') {
        ESP_LOGE(
            TAG,
            "vehicle identity missing"
        );

        return;
    }

    ESP_LOGI(
        TAG,
        "vehicle=%s period_ms=%d",
        s_vehicle_id,
        CONFIG_OCC_RUNTIME_PERIOD_MS
    );

    err =
        occ_mqtt_profile_load(
            &s_mqtt_profile
        );

    if (err != ESP_OK) {
        ESP_LOGW(
            TAG,
            "No valid saved MQTT profile; using default=%s",
            CONFIG_OCC_MQTT_DEFAULT_PROFILE
        );

        err =
            occ_mqtt_profile_from_string(
                CONFIG_OCC_MQTT_DEFAULT_PROFILE,
                &s_mqtt_profile
            );

        if (err != ESP_OK) {
            ESP_LOGE(
                TAG,
                "Invalid default MQTT profile: %s",
                CONFIG_OCC_MQTT_DEFAULT_PROFILE
            );

            return;
        }

        err =
            occ_mqtt_profile_save(
                s_mqtt_profile
            );

        if (err != ESP_OK) {
            ESP_LOGE(
                TAG,
                "Failed to save default MQTT profile: %s",
                esp_err_to_name(err)
            );

            return;
        }
    }


    /* OCC_UNIFIED_STARTUP_COMPAT_V1
     * Diagnostic only: do not change the active MQTT profile.
     */
    occ_protocol_selection_t unified_selection;
    esp_err_t selection_err =
        occ_protocol_selection_load(&unified_selection);

    if (selection_err == ESP_ERR_NVS_NOT_FOUND) {
        ESP_LOGI(
            TAG,
            "Unified selection absent; existing MQTT profile preserved"
        );
    } else if (selection_err != ESP_OK) {
        ESP_LOGE(
            TAG,
            "Unified selection unreadable: %s; MQTT profile unchanged",
            esp_err_to_name(selection_err)
        );
    } else {
        ESP_LOGI(
            TAG,
            "Unified selection stored: protocol=%d security=C%d",
            (int)unified_selection.protocol,
            (int)unified_selection.security
        );

        /* Apply unified MQTT profile before the protocol manager resolves.
         * Old MQTT selection NVS remains synchronized for existing code. */
        if (unified_selection.protocol == OCC_PROTOCOL_MQTT &&
            (int)s_mqtt_profile != (int)unified_selection.security) {
            occ_mqtt_profile_t mode = (occ_mqtt_profile_t)unified_selection.security;
            esp_err_t sync_err = occ_mqtt_profile_save(mode);
            if (sync_err != ESP_OK) {
                ESP_LOGE(TAG, "Unified MQTT compatibility save failed: %s", esp_err_to_name(sync_err));
                return;
            }
            s_mqtt_profile = mode;
            ESP_LOGI(TAG, "Unified MQTT profile active: C%d", (int)mode);
        }
        if (unified_selection.protocol != OCC_PROTOCOL_MQTT ||
            (int)unified_selection.security != (int)s_mqtt_profile) {
            ESP_LOGW(
                TAG,
                "Unified selection differs from running MQTT configuration; "
                "selection is not applied by this compatibility build"
            );
        }
    }



    /* OCC_OPCUA_C0_ONE_TIME_PROVISION */
    {
        occ_protocol_selection_t current;
        esp_err_t selection_rc =
            occ_protocol_selection_load(&current);

        if (selection_rc == ESP_ERR_NVS_NOT_FOUND) {
            occ_protocol_selection_t requested = {
                .protocol = OCC_PROTOCOL_OPCUA,
                .security = OCC_SECURITY_C0
            };

            selection_rc =
                occ_protocol_selection_save(&requested);

            if (selection_rc != ESP_OK) {
                ESP_LOGE(TAG,
                         "C0 provisioning failed: %s",
                         esp_err_to_name(selection_rc));
                return;
            }

            ESP_LOGI(TAG,
                     "One-time OPC UA C0 selection saved");
        } else if (selection_rc != ESP_OK) {
            ESP_LOGE(TAG,
                     "Selection unreadable; refusing overwrite: %s",
                     esp_err_to_name(selection_rc));
            return;
        } else {
            ESP_LOGI(TAG,
                     "Existing unified selection preserved: protocol=%d C%d",
                     (int)current.protocol,
                     (int)current.security);
        }
    }


    /* OCC_VM001_C1_ACTIVATION_V1
     * Controlled C0 -> C1 migration for the physical VM-001 only.
     * Preserve endpoint, Wi-Fi credentials and all other NVS data.
     * Does not overwrite an existing C1 or C2 selection.
     */
    {
        /*
         * OCC_UNIFIED_SWITCHING_FIX:
         * Automatic C0 -> C1 promotion removed.
         * Respect the protocol/security choice already stored in NVS.
         * Do not modify MQTT credentials or security selection here.
         */
    }

    /* OCC_UNIFIED_MANAGER_DISPATCH_V1 */
    occ_protocol_manager_t protocol_manager;

    esp_err_t manager_err = occ_protocol_manager_resolve(
        &protocol_manager,
        (occ_security_t)s_mqtt_profile
    );

    if (manager_err != ESP_OK) {
        ESP_LOGE(
            TAG,
            "Unified protocol selection rejected: %s",
            esp_err_to_name(manager_err)
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

    err =
        occ_endpoint_host_load(
            s_occ_host,
            sizeof(s_occ_host)
        );

    if (err != ESP_OK) {
        ESP_LOGE(
            TAG,
            "OCC endpoint is not provisioned; run device provisioning"
        );

        return;
    }

    ESP_LOGI(
        TAG,
        "Using provisioned OCC endpoint=%s",
        s_occ_host
    );

    /* OCC_OPCUA_BATCH2C_RUNTIME: MQTT branch below is unchanged. */
    /* Independent control-plane starts after Wi-Fi and endpoint provisioning.
     * Never restarts or changes protocol without a valid HMAC command. */
    esp_err_t mgmt_rc = occ_management_start(s_vehicle_id, s_occ_host);
    if (mgmt_rc != ESP_OK) {
        ESP_LOGW(TAG, "Management service unavailable: %s", esp_err_to_name(mgmt_rc));
    }


#if OCC_PARALLEL_DEMO_ENABLED
    if (protocol_manager.backend == OCC_RUNTIME_MQTT) {
        const occ_security_t sec = protocol_manager.selection.security;
        const bool aligned =
            (sec == OCC_SECURITY_C0 && s_mqtt_profile == OCC_MQTT_PROFILE_C0) ||
            (sec == OCC_SECURITY_C1 && s_mqtt_profile == OCC_MQTT_PROFILE_C1) ||
            (sec == OCC_SECURITY_C2 && s_mqtt_profile == OCC_MQTT_PROFILE_C2);
        if (aligned) {
            s_parallel_security = sec;
            ESP_LOGI(TAG,"PARALLEL MQTT+OPCUA+DDS C%d",(int)sec);
            ESP_LOGI(TAG, "PARALLEL deferred until MQTT is ready");
        } else {
            ESP_LOGE(TAG,"PARALLEL blocked: MQTT profile mismatch");
        }
    }
#endif

if (protocol_manager.backend == OCC_RUNTIME_OPCUA_C0 ||
        protocol_manager.backend == OCC_RUNTIME_OPCUA_C1 ||
        protocol_manager.backend == OCC_RUNTIME_OPCUA_C2) {
        const occ_security_t security = protocol_manager.selection.security;
        const int port = 14840 + (int)security;
        /* OCC_PRECRYPTO_PROBE_V1: stops BEFORE C1 cryptographic client creation. */
        /* OCC C1: pre-crypto diagnostic bypass disabled for real protocol test. */
        char opcua_url[256];
        int n = snprintf(opcua_url, sizeof(opcua_url),
                         "opc.tcp://%s:%d", s_occ_host, port);
        if (n <= 0 || n >= (int)sizeof(opcua_url)) {
            ESP_LOGE(TAG, "OPC UA endpoint length invalid");
            return;
        }
        ESP_LOGI(TAG, "Starting OPC UA C%d on gateway port %d",
                 (int)security, port);
        esp_err_t rc = occ_opcua_run(s_vehicle_id, opcua_url, security);
        ESP_LOGE(TAG, "OPC UA runtime stopped: %s", esp_err_to_name(rc));
        return;
    }
    /* OCC_DDS_C0_STREAM_V1: authenticated control still starts above. */
    if (protocol_manager.backend == OCC_RUNTIME_DDS_C0 ||
        protocol_manager.backend == OCC_RUNTIME_DDS_C1 ||
        protocol_manager.backend == OCC_RUNTIME_DDS_C2) {
        const int security = (int)protocol_manager.selection.security;
        ESP_LOGI(TAG, "Starting DDS C%d", security);
        esp_err_t rc = occ_dds_run(s_vehicle_id, s_occ_host, security);
        ESP_LOGE(TAG, "DDS C0 runtime ended: %s", esp_err_to_name(rc));
        return;
    }
    if (protocol_manager.backend != OCC_RUNTIME_MQTT) {
        ESP_LOGE(TAG, "Unsupported unified backend");
        return;
    }
    ESP_LOGI(TAG, "Unified manager selected MQTT C%d",
             (int)protocol_manager.selection.security);

    const char *scheme = NULL;
    int port = 0;

    switch (s_mqtt_profile) {
        case OCC_MQTT_PROFILE_C0:
            scheme = "mqtt";
            port = 1883;
            break;

        case OCC_MQTT_PROFILE_C1:
            scheme = "mqtt";
            port = 1884;
            break;

        case OCC_MQTT_PROFILE_C2:
            scheme = "mqtts";
            port = 8883;
            break;

        default:
            ESP_LOGE(
                TAG,
                "Unsupported MQTT profile"
            );

            return;
    }

    const int uri_len =
        snprintf(
            s_broker_uri,
            sizeof(s_broker_uri),
            "%s://%s:%d",
            scheme,
            s_occ_host,
            port
        );

    if (
        uri_len <= 0 ||
        uri_len >=
            (int)sizeof(s_broker_uri)
    ) {
        ESP_LOGE(
            TAG,
            "MQTT broker URI construction failed"
        );

        return;
    }

    const char *broker_uri =
        s_broker_uri;

    ESP_LOGI(
        TAG,
        "MQTT destination profile=%s host=%s port=%d",
        occ_mqtt_profile_to_string(
            s_mqtt_profile
        ),
        s_occ_host,
        port
    );

    if (s_mqtt_profile == OCC_MQTT_PROFILE_C2) {
        if (
            fair_v1_c2_ca_crt_start[0] == '\0'
        ) {
            ESP_LOGE(
                TAG,
                "C2 requires a CA certificate"
            );

            return;
        }

        const char *sntp_servers[] = {
            CONFIG_OCC_SNTP_PRIMARY_SERVER,
            s_occ_host
        };

        while (true) {
            bool time_synced = false;

            for (
                size_t server_index = 0;
                server_index <
                    sizeof(sntp_servers) /
                    sizeof(sntp_servers[0]);
                ++server_index
            ) {
                const char *server =
                    sntp_servers[server_index];

                if (
                    server == NULL ||
                    server[0] == '\0'
                ) {
                    continue;
                }

                if (
                    server_index > 0 &&
                    strcmp(
                        server,
                        sntp_servers[0]
                    ) == 0
                ) {
                    continue;
                }

                ESP_LOGI(
                    TAG,
                    "C2 SNTP attempting server=%s",
                    server
                );

                esp_sntp_config_t sntp_config =
                    ESP_NETIF_SNTP_DEFAULT_CONFIG(
                        server
                    );

                err =
                    esp_netif_sntp_init(
                        &sntp_config
                    );

                if (err != ESP_OK) {
                    ESP_LOGW(
                        TAG,
                        "C2 SNTP initialization failed server=%s: %s",
                        server,
                        esp_err_to_name(err)
                    );

                    continue;
                }

                err =
                    esp_netif_sntp_sync_wait(
                        pdMS_TO_TICKS(30000)
                    );

                esp_netif_sntp_deinit();

                if (err == ESP_OK) {
                    ESP_LOGI(
                        TAG,
                        "C2 SNTP synchronization complete server=%s",
                        server
                    );

                    time_synced = true;
                    break;
                }

                ESP_LOGW(
                    TAG,
                    "C2 SNTP synchronization failed server=%s: %s",
                    server,
                    esp_err_to_name(err)
                );
            }

            if (time_synced) {
                break;
            }

            ESP_LOGW(
                TAG,
                "C2 SNTP sources unavailable; vehicle remains active; retrying"
            );

            vTaskDelay(
                pdMS_TO_TICKS(5000)
            );
        }
    }

    /*
     * Authentication is required for C1 and C2.
     * C0 intentionally has no MQTT credentials.
     */
    if (s_mqtt_profile != OCC_MQTT_PROFILE_C0) {
        err =
            occ_mqtt_credentials_load(
                &s_mqtt_credentials
            );

        if (err != ESP_OK) {
            ESP_LOGE(
                TAG,
                "%s MQTT credentials not provisioned: %s",
                occ_mqtt_profile_to_string(
                    s_mqtt_profile
                ),
                esp_err_to_name(err)
            );

            return;
        }
    }

    esp_mqtt_client_config_t mqtt_config = {
        .broker.address.uri = broker_uri,
    };

    if (s_mqtt_profile != OCC_MQTT_PROFILE_C0) {
        mqtt_config.credentials.username =
            s_mqtt_credentials.username;

        mqtt_config.credentials.authentication.password =
            s_mqtt_credentials.password;
    }

    if (s_mqtt_profile == OCC_MQTT_PROFILE_C2) {
        mqtt_config.broker.verification.certificate =
            fair_v1_c2_ca_crt_start;

        mqtt_config.broker.verification.common_name =
            CONFIG_OCC_TLS_SERVER_NAME;
    }

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

    TickType_t last_wake =
        xTaskGetTickCount();

    const TickType_t period_ticks =
        pdMS_TO_TICKS(
            CONFIG_OCC_RUNTIME_PERIOD_MS
        );

    uint32_t waiting_log_counter = 0U;

    /* Only submit fresh normal telemetry samples. */
    bool have_last_submitted_seq = false;
    uint32_t last_submitted_seq = 0U;
    /* OCC_PARALLEL_MQTT_FIRST_V1 */
#if OCC_PARALLEL_DEMO_ENABLED
    bool parallel_started = false;
    TickType_t parallel_ready_since = 0;
#endif


    while (true) {
#if OCC_PARALLEL_DEMO_ENABLED
        if (!parallel_started) {
            /* OCC_PARALLEL_MQTT_ECHO_GATE_V2:
                 * MQTT telemetry readiness is sufficient.
                 * Control subscription is independent. */
            if (s_mqtt_connected &&
                s_echo_subscribed) {

                TickType_t now_tick = xTaskGetTickCount();

                if (parallel_ready_since == 0) {
                    parallel_ready_since = now_tick;
                    ESP_LOGI(TAG,
                        "PARALLEL MQTT connected; stability timer started");
                } else if (
                    (TickType_t)(now_tick - parallel_ready_since)
                    >= pdMS_TO_TICKS(10000)
                ) {
                    parallel_started = true;
                    ESP_LOGI(TAG,
                        "PARALLEL MQTT stable; starting extra protocols");
                    occ_parallel_demo_start();
                }
            } else {
                parallel_ready_since = 0;
            }
        }
#endif

        if (
            s_mqtt_connected &&
            s_control_subscribed &&
            !s_runtime_status_published
        ) {
            publish_profile_status(
                "online",
                s_mqtt_profile
            );

            ESP_LOGI(
                TAG,
                "runtime status online profile=%s",
                occ_mqtt_profile_to_string(
                    s_mqtt_profile
                )
            );

            s_runtime_status_published = true;
        }

        if (s_vehicle_id_change_pending) {
            char requested_vehicle_id[
                OCC_VEHICLE_ID_MAX_LEN
            ];

            const int copied =
                snprintf(
                    requested_vehicle_id,
                    sizeof(requested_vehicle_id),
                    "%s",
                    s_requested_vehicle_id
                );

            s_vehicle_id_change_pending = false;

            if (
                copied <= 0 ||
                copied >=
                    (int)sizeof(requested_vehicle_id)
            ) {
                ESP_LOGE(
                    TAG,
                    "pending vehicle identity is invalid"
                );
            } else if (
                strcmp(
                    requested_vehicle_id,
                    s_vehicle_id
                ) == 0
            ) {
                ESP_LOGI(
                    TAG,
                    "requested vehicle identity already active: %s",
                    requested_vehicle_id
                );

                publish_vehicle_id_status(
                    "vehicle_id_already_active",
                    requested_vehicle_id
                );
            } else {
                esp_err_t vehicle_id_err =
                    occ_vehicle_id_save(
                        requested_vehicle_id
                    );

                if (vehicle_id_err != ESP_OK) {
                    ESP_LOGE(
                        TAG,
                        "failed to save requested vehicle identity: %s",
                        esp_err_to_name(
                            vehicle_id_err
                        )
                    );

                    publish_vehicle_id_status(
                        "vehicle_id_save_failed",
                        requested_vehicle_id
                    );
                } else {
                    ESP_LOGI(
                        TAG,
                        "vehicle identity saved; switching %s -> %s",
                        s_vehicle_id,
                        requested_vehicle_id
                    );

                    publish_vehicle_id_status(
                        "vehicle_id_switching",
                        requested_vehicle_id
                    );

                    /*
                     * Give the QoS1 status message time to leave
                     * before rebuilding identity-derived topics.
                     */
                    vTaskDelay(
                        pdMS_TO_TICKS(750)
                    );

                    esp_restart();
                }
            }
        }

        if (s_credentials_clear_pending) {
            s_credentials_clear_pending = false;

            esp_err_t credentials_err =
                occ_mqtt_credentials_clear();

            if (credentials_err != ESP_OK) {
                ESP_LOGE(
                    TAG,
                    "failed to clear MQTT credentials: %s",
                    esp_err_to_name(
                        credentials_err
                    )
                );

                publish_credentials_status(
                    "credentials_clear_failed"
                );
            } else {
                ESP_LOGI(
                    TAG,
                    "MQTT credentials cleared; entering reprovisioning"
                );

                publish_credentials_status(
                    "credentials_cleared_reprovisioning"
                );

                /*
                 * Give the QoS1 status message time to leave
                 * before restarting into provisioning mode.
                 */
                vTaskDelay(
                    pdMS_TO_TICKS(750)
                );

                esp_restart();
            }
        }

        if (s_wifi_reprovision_pending) {
            s_wifi_reprovision_pending = false;

            ESP_LOGI(
                TAG,
                "Restarting into Wi-Fi provisioning mode"
            );

            vTaskDelay(
                pdMS_TO_TICKS(750)
            );

            esp_restart();
        }

        if (s_endpoint_change_pending) {
            s_endpoint_change_pending = false;

            esp_err_t endpoint_err =
                occ_endpoint_host_save(
                    s_requested_occ_host
                );

            if (endpoint_err != ESP_OK) {
                ESP_LOGE(
                    TAG,
                    "Failed to save OCC endpoint: %s",
                    esp_err_to_name(
                        endpoint_err
                    )
                );
            } else {
                ESP_LOGI(
                    TAG,
                    "OCC endpoint saved; restarting runtime"
                );

                vTaskDelay(
                    pdMS_TO_TICKS(750)
                );

                esp_restart();
            }
        }

        if (s_profile_change_pending) {
            const occ_mqtt_profile_t requested_profile =
                s_requested_profile;

            s_profile_change_pending = false;

            if (
                requested_profile ==
                s_mqtt_profile
            ) {
                ESP_LOGI(
                    TAG,
                    "requested profile already active: %s",
                    occ_mqtt_profile_to_string(
                        requested_profile
                    )
                );

                publish_profile_status(
                    "already_active",
                    requested_profile
                );
            } else {
                esp_err_t profile_err =
                    occ_mqtt_profile_save(
                        requested_profile
                    );

                if (profile_err != ESP_OK) {
                    ESP_LOGE(
                        TAG,
                        "failed to save requested profile: %s",
                        esp_err_to_name(
                            profile_err
                        )
                    );

                    publish_profile_status(
                        "save_failed",
                        requested_profile
                    );
                } else {
                    ESP_LOGI(
                        TAG,
                        "profile saved; switching %s -> %s",
                        occ_mqtt_profile_to_string(
                            s_mqtt_profile
                        ),
                        occ_mqtt_profile_to_string(
                            requested_profile
                        )
                    );

                    /* Maintain unified NVS compatibility for legacy MQTT commands. */
                    occ_protocol_selection_t new_unified = {
                        .protocol = OCC_PROTOCOL_MQTT,
                        .security = (occ_security_t)requested_profile
                    };
                    esp_err_t unified_err = occ_protocol_selection_save(&new_unified);
                    if (unified_err != ESP_OK) {
                        ESP_LOGE(TAG, "Cannot sync unified profile; refusing reboot: %s",
                                 esp_err_to_name(unified_err));
                        publish_profile_status("unified_save_failed", requested_profile);
                        continue;
                    }
                    publish_profile_status(
                        "switching",
                        requested_profile
                    );

                    /*
                     * Give the QoS1 status message time to leave
                     * the client before the controlled restart.
                     */
                    vTaskDelay(
                        pdMS_TO_TICKS(750)
                    );

                    esp_restart();
                }
            }
        }

        if (
            s_mqtt_connected &&
            s_echo_subscribed
        ) {
            char payload[
                PAYLOAD_BUFFER_BYTES
            ];

            uint32_t publish_seq = 0U;

            const int payload_len =
                build_payload(
                    payload,
                    sizeof(payload),
                    &publish_seq
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
            } else if (
                have_last_submitted_seq &&
                publish_seq <= last_submitted_seq
            ) {
                /* State task has not produced a newer sample yet. */
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
                    last_submitted_seq = publish_seq;
                    have_last_submitted_seq = true;
                    if (
                        publish_seq % 100U == 0U
                    ) {
                        ESP_LOGI(
                            TAG,
                            "telemetry seq=%" PRIu32
                            " mqtt_id=%d",
                            publish_seq,
                            rc
                        );
                    }
                } else {
                    ESP_LOGW(
                        TAG,
                        "telemetry enqueue failed seq=%"
                        PRIu32,
                        publish_seq
                    );
                }
            }

            /*
             * There is intentionally no transport-side
             * sequence increment here.
             *
             * VehicleState owns sequence progression and
             * continues advancing while MQTT is offline.
             *
             * After reconnect we send the LATEST state,
             * never a burst of stale queued states.
             */

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
