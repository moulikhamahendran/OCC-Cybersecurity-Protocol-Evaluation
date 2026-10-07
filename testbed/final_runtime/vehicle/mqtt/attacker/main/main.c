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
#include "driver/gpio.h"
#include "mqtt_client.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "runtime_wifi.h"
#include "runtime_mqtt_config.h"
#include "runtime_endpoint_config.h"
#include "runtime_known_wifi.h"
#include "attack_controller.h"
#include "attack_publish_wrapper.h"
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


static void publish_attack_controller_status(
    const char *result
);

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


    if (
        strcmp(
            command->valuestring,
            "arm_attack"
        ) == 0
    ) {
        /*
         * Attacker controller is remotely administrated only
         * through authenticated + TLS-protected C2.
         */
        if (
            s_mqtt_profile !=
                OCC_MQTT_PROFILE_C2
        ) {
            ESP_LOGW(
                TAG,
                "attack arm rejected: C2 required"
            );

            cJSON_Delete(root);
            return;
        }

        const cJSON *mode_json =
            cJSON_GetObjectItemCaseSensitive(
                root,
                "mode"
            );

        if (
            !cJSON_IsString(mode_json) ||
            mode_json->valuestring == NULL
        ) {
            ESP_LOGW(
                TAG,
                "attack arm rejected: mode missing"
            );

            cJSON_Delete(root);
            return;
        }

        occ_attack_mode_t mode;

        if (
            !occ_attack_mode_from_string(
                mode_json->valuestring,
                &mode
            ) ||
            mode == OCC_ATTACK_MODE_IDLE
        ) {
            ESP_LOGW(
                TAG,
                "attack arm rejected: invalid mode"
            );

            cJSON_Delete(root);
            return;
        }

        esp_err_t attack_err =
            occ_attack_controller_arm(
                mode
            );

        if (attack_err != ESP_OK) {
            ESP_LOGW(
                TAG,
                "attack controller arm failed: %s",
                esp_err_to_name(
                    attack_err
                )
            );

            cJSON_Delete(root);
            return;
        }

        ESP_LOGI(
            TAG,
            "attack controller armed mode=%s execution_enabled=true",
            occ_attack_mode_to_string(
                mode
            )
        );

        publish_attack_controller_status(
            "armed_ready"
        );

        cJSON_Delete(root);
        return;
    }

    if (
        strcmp(
            command->valuestring,
            "stop_attack"
        ) == 0
    ) {
        occ_attack_controller_stop();

        ESP_LOGI(
            TAG,
            "attack controller stopped mode=IDLE execution_enabled=false"
        );

        publish_attack_controller_status(
            "stopped_idle"
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



static void publish_attack_controller_status(
    const char *result
)
{
    if (
        s_client == NULL ||
        result == NULL
    ) {
        return;
    }

    const occ_attack_mode_t mode =
        occ_attack_controller_mode();

    char status[STATUS_BUFFER_BYTES];

    const int status_len =
        snprintf(
            status,
            sizeof(status),
            "{"
            "\"vehicle_id\":\"%s\","
            "\"attacker_hardware_unit_id\":\"ESP32_3\","
            "\"physical_mac\":\"94:3c:c6:32:05:80\","
            "\"attack_mode\":\"%s\","
            "\"controller_result\":\"%s\","
            "\"execution_enabled\":%s"
            "}",
            s_vehicle_id,
            occ_attack_mode_to_string(mode),
            result,
            occ_attack_execution_enabled()
                ? "true"
                : "false"
        );

    if (
        status_len <= 0 ||
        status_len >=
            (int)sizeof(status)
    ) {
        ESP_LOGW(
            TAG,
            "attack controller status construction failed"
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
            "attack controller status publish failed"
        );
    }
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


static void execute_armed_attack_once(void)
{
    const occ_attack_mode_t mode =
        occ_attack_controller_mode();

    if (mode == OCC_ATTACK_MODE_IDLE) {
        return;
    }

    if (
        s_client == NULL ||
        !s_mqtt_connected
    ) {
        return;
    }

    /*
     * MALFORMED is generated explicitly by this function.
     *
     * REPLAY, SPOOF and FLOOD are deliberately executed by
     * attack_publish_wrapper.h when the next VM-003 telemetry
     * publication reaches the MQTT transport.
     *
     * Therefore DO NOT stop those modes here.
     */
    if (mode != OCC_ATTACK_MODE_MALFORMED) {
        return;
    }

    /*
     * Deliberately invalid/truncated JSON.
     */
    char payload[160];

    const int payload_len =
        snprintf(
            payload,
            sizeof(payload),
            "{"
            "\"schema_ver\":\"runtime-1.0\","
            "\"serialNumber\":\"%s\","
            "\"seq\":",
            s_vehicle_id
        );

    if (
        payload_len <= 0 ||
        payload_len >= (int)sizeof(payload)
    ) {
        ESP_LOGE(
            TAG,
            "MALFORMED payload construction failed"
        );

        occ_attack_controller_stop();
        return;
    }

    ESP_LOGW(
        TAG,
        "ATTACK_START mode=MALFORMED vehicle=%s",
        s_vehicle_id
    );

    publish_attack_controller_status(
        "attack_start"
    );

    const int msg_id =
        esp_mqtt_client_publish(
            s_client,
            s_telemetry_topic,
            payload,
            payload_len,
            OCC_MQTT_QOS,
            0
        );

    if (msg_id >= 0) {
        ESP_LOGW(
            TAG,
            "ATTACK_ACTION mode=MALFORMED mqtt_id=%d",
            msg_id
        );

        publish_attack_controller_status(
            "attack_action_sent"
        );
    } else {
        ESP_LOGE(
            TAG,
            "ATTACK_ACTION mode=MALFORMED publish_failed"
        );

        publish_attack_controller_status(
            "attack_action_failed"
        );
    }

    ESP_LOGW(
        TAG,
        "ATTACK_STOP mode=MALFORMED"
    );

    publish_attack_controller_status(
        "attack_stop"
    );

    /*
     * One-shot bounded attack.
     */
    occ_attack_controller_stop();

    publish_attack_controller_status(
        "idle_after_attack"
    );
}


void app_main(void)
{
    ESP_LOGI(
        TAG,
        "OCC MQTT VM-003 attacker runtime starting - MALFORMED/REPLAY/SPOOF/FLOOD enabled"
    );

    occ_attack_controller_init();

    ESP_LOGI(
        TAG,
        "attack controller initialized mode=%s execution_enabled=%s",
        occ_attack_mode_to_string(
            occ_attack_controller_mode()
        ),
        occ_attack_execution_enabled()
            ? "true"
            : "false"
    );

    esp_err_t err =
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

    /*
     * Dedicated attacker hardware role.
     *
     * ESP32 #3 must remain attributable to VM-003.
     * This writes only the OCC vehicle_id key.
     * NVS is NOT erased.
     */
    err =
        occ_vehicle_id_save(
            CONFIG_OCC_VEHICLE_ID
        );

    if (err != ESP_OK) {
        ESP_LOGE(
            TAG,
            "Failed to enforce attacker identity: %s",
            esp_err_to_name(err)
        );

        return;
    }

    ESP_LOGI(
        TAG,
        "Dedicated attacker identity enforced=%s",
        CONFIG_OCC_VEHICLE_ID
    );

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

    /*
     * First VM-003 qualification uses C2 only.
     *
     * No attack mode is enabled in this build.
     */
    err =
        occ_mqtt_profile_save(
            OCC_MQTT_PROFILE_C2
        );

    if (err != ESP_OK) {
        ESP_LOGE(
            TAG,
            "Failed to enforce attacker C2 profile: %s",
            esp_err_to_name(err)
        );

        return;
    }

    ESP_LOGI(
        TAG,
        "Dedicated attacker profile enforced=C2"
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

        /*
         * Execute one explicitly armed bounded attack.
         */
        execute_armed_attack_once();

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
            } else {
                /*
                 * Dedicated VM-003 attacker runtime:
                 *
                 * use publish() so attack_publish_wrapper.h can
                 * intercept this telemetry publication.
                 *
                 * Normal VM-001/VM-002 selectable runtimes are
                 * not modified.
                 */
                const int rc =
                    esp_mqtt_client_publish(
                        s_client,
                        s_telemetry_topic,
                        payload,
                        payload_len,
                        OCC_MQTT_QOS,
                        0
                    );

                if (rc >= 0) {
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
