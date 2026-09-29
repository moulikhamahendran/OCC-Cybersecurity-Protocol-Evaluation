#include <errno.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

#include "esp_err.h"
#include "esp_log.h"

#include "freertos/FreeRTOS.h"

#include "fair_mqtt_profile.h"
#include "fair_mqtt_network.h"
#include "fair_mqtt_transport.h"
#include "fair_mqtt_benchmark.h"

static const char *TAG =
    "FAIR_MQTT_MAIN";

static bool starts_with(
    const char *value,
    const char *prefix
)
{
    if (
        value == NULL ||
        prefix == NULL
    ) {
        return false;
    }

    return
        strncmp(
            value,
            prefix,
            strlen(prefix)
        ) == 0;
}

static bool parse_float_value(
    const char *text,
    float *out
)
{
    if (
        text == NULL ||
        text[0] == '\0' ||
        out == NULL
    ) {
        return false;
    }

    errno = 0;

    char *end = NULL;

    const float value =
        strtof(
            text,
            &end
        );

    if (
        errno != 0 ||
        end == text ||
        end == NULL ||
        *end != '\0'
    ) {
        return false;
    }

    *out =
        value;

    return true;
}

static bool workload_configured(
    fair_mqtt_benchmark_config_t *config
)
{
    if (
        config == NULL ||
        strlen(CONFIG_FAIR_RUN_ID) == 0U ||
        strlen(CONFIG_FAIR_WORKLOAD_SPEED) == 0U ||
        strlen(CONFIG_FAIR_WORKLOAD_POS_X) == 0U ||
        strlen(CONFIG_FAIR_WORKLOAD_POS_Y) == 0U ||
        strlen(CONFIG_FAIR_WORKLOAD_HEADING) == 0U ||
        strlen(CONFIG_FAIR_WORKLOAD_BATTERY_PCT) == 0U ||
        strlen(CONFIG_FAIR_WORKLOAD_STATE) == 0U
    ) {
        return false;
    }

    config->run_id =
        CONFIG_FAIR_RUN_ID;

    config->profile_name =
        FAIR_MQTT_PROFILE_NAME;

    config->repeat_index =
        CONFIG_FAIR_REPEAT_INDEX;

    config->serial_number =
        "VM-001";

    config->state =
        CONFIG_FAIR_WORKLOAD_STATE;

    return
        parse_float_value(
            CONFIG_FAIR_WORKLOAD_SPEED,
            &config->speed
        ) &&
        parse_float_value(
            CONFIG_FAIR_WORKLOAD_POS_X,
            &config->pos_x
        ) &&
        parse_float_value(
            CONFIG_FAIR_WORKLOAD_POS_Y,
            &config->pos_y
        ) &&
        parse_float_value(
            CONFIG_FAIR_WORKLOAD_HEADING,
            &config->heading
        ) &&
        parse_float_value(
            CONFIG_FAIR_WORKLOAD_BATTERY_PCT,
            &config->battery_pct
        );
}

void app_main(void)
{
    if (
        strlen(CONFIG_FAIR_WIFI_SSID) == 0U ||
        strlen(CONFIG_FAIR_MQTT_BROKER_URI) == 0U
    ) {
        ESP_LOGW(
            TAG,
            "%s compile-only build: Wi-Fi/broker not configured",
            FAIR_MQTT_PROFILE_NAME
        );

        return;
    }

#if FAIR_MQTT_PROFILE_USE_TLS
    if (
        !starts_with(
            CONFIG_FAIR_MQTT_BROKER_URI,
            "mqtts://"
        )
    ) {
        ESP_LOGE(
            TAG,
            "C2 requires mqtts:// broker URI"
        );

        return;
    }
#else
    if (
        !starts_with(
            CONFIG_FAIR_MQTT_BROKER_URI,
            "mqtt://"
        )
    ) {
        ESP_LOGE(
            TAG,
            "%s requires mqtt:// broker URI",
            FAIR_MQTT_PROFILE_NAME
        );

        return;
    }
#endif

#if FAIR_MQTT_PROFILE_USE_AUTH
    if (
        strlen(CONFIG_FAIR_MQTT_USERNAME) == 0U ||
        strlen(CONFIG_FAIR_MQTT_PASSWORD) == 0U
    ) {
        ESP_LOGE(
            TAG,
            "%s requires username/password",
            FAIR_MQTT_PROFILE_NAME
        );

        return;
    }
#endif

#if FAIR_MQTT_PROFILE_USE_TLS
    if (
        strlen(CONFIG_FAIR_MQTT_CA_CERT_PEM) == 0U ||
        strlen(CONFIG_FAIR_SNTP_SERVER) == 0U
    ) {
        ESP_LOGE(
            TAG,
            "C2 requires CA certificate and SNTP server"
        );

        return;
    }
#endif

    fair_mqtt_benchmark_config_t
        benchmark_config = {0};

    if (
        !workload_configured(
            &benchmark_config
        )
    ) {
        ESP_LOGW(
            TAG,
            "FAIR workload values are not configured; refusing runtime benchmark"
        );

        return;
    }

    esp_err_t err =
        fair_mqtt_network_connect(
            CONFIG_FAIR_WIFI_SSID,
            CONFIG_FAIR_WIFI_PASSWORD,
            pdMS_TO_TICKS(30000)
        );

    if (
        err != ESP_OK
    ) {
        ESP_LOGE(
            TAG,
            "Wi-Fi setup failed: %s",
            esp_err_to_name(err)
        );

        return;
    }

#if FAIR_MQTT_PROFILE_USE_TLS
    err =
        fair_mqtt_network_sync_time(
            CONFIG_FAIR_SNTP_SERVER,
            pdMS_TO_TICKS(30000)
        );

    if (
        err != ESP_OK
    ) {
        ESP_LOGE(
            TAG,
            "C2 SNTP synchronization failed: %s",
            esp_err_to_name(err)
        );

        return;
    }
#endif

    fair_mqtt_transport_t transport = {0};

    const fair_mqtt_transport_config_t
        transport_config = {
            .broker_uri =
                CONFIG_FAIR_MQTT_BROKER_URI,

            .serial_number =
                "VM-001",

            .use_authentication =
                FAIR_MQTT_PROFILE_USE_AUTH != 0,

            .use_tls =
                FAIR_MQTT_PROFILE_USE_TLS != 0,

            .username =
                CONFIG_FAIR_MQTT_USERNAME,

            .password =
                CONFIG_FAIR_MQTT_PASSWORD,

            .ca_certificate_pem =
                CONFIG_FAIR_MQTT_CA_CERT_PEM,
        };

    err =
        fair_mqtt_transport_init(
            &transport,
            &transport_config
        );

    if (
        err != ESP_OK
    ) {
        ESP_LOGE(
            TAG,
            "MQTT init failed: %s",
            esp_err_to_name(err)
        );

        return;
    }

    err =
        fair_mqtt_transport_start(
            &transport
        );

    if (
        err != ESP_OK
    ) {
        ESP_LOGE(
            TAG,
            "MQTT start failed: %s",
            esp_err_to_name(err)
        );

        return;
    }

    ESP_LOGI(
        TAG,
        "formal MQTT %s started",
        FAIR_MQTT_PROFILE_NAME
    );

    err =
        fair_mqtt_benchmark_run(
            &transport,
            &benchmark_config
        );

    if (
        err != ESP_OK
    ) {
        ESP_LOGE(
            TAG,
            "FAIR benchmark failed: %s",
            esp_err_to_name(err)
        );

        return;
    }

    ESP_LOGI(
        TAG,
        "FAIR MQTT %s benchmark complete",
        FAIR_MQTT_PROFILE_NAME
    );
}
