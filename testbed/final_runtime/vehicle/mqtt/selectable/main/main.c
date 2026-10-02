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
#include "mqtt_client.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "runtime_wifi.h"
#include "runtime_mqtt_config.h"


extern const char fair_v1_c2_ca_crt_start[]
    asm("_binary_fair_v1_c2_ca_crt_start");

#define OCC_MQTT_QOS 1
#define TOPIC_BUFFER_BYTES 128
#define PAYLOAD_BUFFER_BYTES 384
#define ECHO_BUFFER_BYTES 192
#define CONTROL_BUFFER_BYTES 192
#define STATUS_BUFFER_BYTES 192

static const char *TAG = "OCC_MQTT_RUNTIME";

static esp_mqtt_client_handle_t s_client = NULL;

static occ_mqtt_credentials_t s_mqtt_credentials;
static occ_mqtt_profile_t s_mqtt_profile;

static volatile bool s_mqtt_connected = false;
static volatile bool s_echo_subscribed = false;
static volatile bool s_control_subscribed = false;

static int s_echo_sub_msg_id = -1;
static int s_control_sub_msg_id = -1;

static char s_vehicle_id[OCC_VEHICLE_ID_MAX_LEN];

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
            s_profile_change_pending ||
            s_vehicle_id_change_pending
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
            s_profile_change_pending ||
            s_vehicle_id_change_pending
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
    int telemetry_len =
        snprintf(
            s_telemetry_topic,
            sizeof(s_telemetry_topic),
            "fair/v1/%s/telemetry",
            s_vehicle_id
        );

    int echo_len =
        snprintf(
            s_echo_topic,
            sizeof(s_echo_topic),
            "fair/v1/%s/echo",
            s_vehicle_id
        );

    int control_len =
        snprintf(
            s_control_topic,
            sizeof(s_control_topic),
            "occ/runtime/%s/control",
            s_vehicle_id
        );

    int status_len =
        snprintf(
            s_status_topic,
            sizeof(s_status_topic),
            "occ/runtime/%s/status",
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
        s_vehicle_id,
        seq,
        t_source_us
    );
}


void app_main(void)
{
    ESP_LOGI(
        TAG,
        "OCC MQTT selectable operational runtime starting"
    );

    esp_err_t err =
        occ_runtime_wifi_connect_or_provision();

    if (err != ESP_OK) {
        ESP_LOGE(
            TAG,
            "Wi-Fi provisioning/connect failed: %s",
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

    if (!build_topics()) {
        ESP_LOGE(
            TAG,
            "MQTT topic construction failed"
        );

        return;
    }

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

    const char *broker_uri = NULL;

    switch (s_mqtt_profile) {
        case OCC_MQTT_PROFILE_C0:
            broker_uri =
                CONFIG_OCC_MQTT_C0_BROKER_URI;
            break;

        case OCC_MQTT_PROFILE_C1:
            broker_uri =
                CONFIG_OCC_MQTT_C1_BROKER_URI;
            break;

        case OCC_MQTT_PROFILE_C2:
            broker_uri =
                CONFIG_OCC_MQTT_C2_BROKER_URI;
            break;

        default:
            ESP_LOGE(
                TAG,
                "Unsupported MQTT profile"
            );

            return;
    }

    if (
        broker_uri == NULL ||
        broker_uri[0] == '\0'
    ) {
        ESP_LOGE(
            TAG,
            "broker URI missing for profile=%s",
            occ_mqtt_profile_to_string(
                s_mqtt_profile
            )
        );

        return;
    }

    ESP_LOGI(
        TAG,
        "profile=%s broker=%s",
        occ_mqtt_profile_to_string(
            s_mqtt_profile
        ),
        broker_uri
    );

    /*
     * C2 requires valid time before TLS server
     * certificate verification.
     */
    if (s_mqtt_profile == OCC_MQTT_PROFILE_C2) {
        if (
            strlen(CONFIG_OCC_SNTP_SERVER) == 0U ||
            fair_v1_c2_ca_crt_start[0] == '\0'
        ) {
            ESP_LOGE(
                TAG,
                "C2 requires SNTP server and CA certificate"
            );

            return;
        }

        esp_sntp_config_t sntp_config =
            ESP_NETIF_SNTP_DEFAULT_CONFIG(
                CONFIG_OCC_SNTP_SERVER
            );

        err =
            esp_netif_sntp_init(
                &sntp_config
            );

        if (err != ESP_OK) {
            ESP_LOGE(
                TAG,
                "C2 SNTP initialization failed: %s",
                esp_err_to_name(err)
            );

            return;
        }

        err =
            esp_netif_sntp_sync_wait(
                pdMS_TO_TICKS(30000)
            );

        esp_netif_sntp_deinit();

        if (err != ESP_OK) {
            ESP_LOGE(
                TAG,
                "C2 SNTP synchronization failed: %s",
                esp_err_to_name(err)
            );

            return;
        }

        ESP_LOGI(
            TAG,
            "C2 SNTP synchronization complete"
        );
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
