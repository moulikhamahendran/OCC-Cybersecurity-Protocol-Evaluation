#include <errno.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

#include "esp_err.h"
#include "esp_log.h"

#include "freertos/FreeRTOS.h"

#include "open62541.h"

#include "fair_opcua_profile.h"
#include "fair_opcua_network.h"
#include "fair_opcua_transport.h"
#include "fair_opcua_benchmark.h"

static const char *TAG =
    "FAIR_OPCUA_MAIN";

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

static bool fair_workload_configured(
    fair_opcua_benchmark_config_t *config
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
        FAIR_OPCUA_PROFILE_NAME;

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
        strlen(CONFIG_FAIR_OPCUA_ENDPOINT) == 0U
    ) {
        ESP_LOGW(
            TAG,
            "%s compile-only state",
            FAIR_OPCUA_PROFILE_NAME
        );

        return;
    }

#if FAIR_OPCUA_PROFILE_SECURE
    if (
        strlen(CONFIG_FAIR_OPCUA_USERNAME) == 0U ||
        strlen(CONFIG_FAIR_OPCUA_PASSWORD) == 0U ||
        strlen(CONFIG_FAIR_SNTP_SERVER) == 0U
    ) {
        ESP_LOGE(
            TAG,
            "%s requires username, password and SNTP",
            FAIR_OPCUA_PROFILE_NAME
        );

        return;
    }
#endif

    fair_opcua_benchmark_config_t
        benchmark_config = {0};

    if (
        !fair_workload_configured(
            &benchmark_config
        )
    ) {
        ESP_LOGW(
            TAG,
            "FAIR workload not configured; refusing benchmark runtime"
        );

        return;
    }

    esp_err_t err =
        fair_opcua_network_connect(
            CONFIG_FAIR_WIFI_SSID,
            CONFIG_FAIR_WIFI_PASSWORD,
            pdMS_TO_TICKS(30000)
        );

    if (
        err != ESP_OK
    ) {
        ESP_LOGE(
            TAG,
            "Wi-Fi failed: %s",
            esp_err_to_name(err)
        );

        return;
    }

#if FAIR_OPCUA_PROFILE_SECURE
    err =
        fair_opcua_network_sync_time(
            CONFIG_FAIR_SNTP_SERVER,
            pdMS_TO_TICKS(30000)
        );

    if (
        err != ESP_OK
    ) {
        ESP_LOGE(
            TAG,
            "SNTP failed: %s",
            esp_err_to_name(err)
        );

        return;
    }
#endif

    UA_Client *client =
        fair_opcua_profile_create_client();

    if (
        client == NULL
    ) {
        ESP_LOGE(
            TAG,
            "profile client creation failed"
        );

        return;
    }

    fair_opcua_transport_t transport;

    if (
        !fair_opcua_transport_init(
            &transport,
            client,
            CONFIG_FAIR_OPCUA_ENDPOINT,
            "VM-001"
        )
    ) {
        UA_Client_delete(client);
        return;
    }

    UA_StatusCode ua_rc =
        fair_opcua_transport_connect(
            &transport
        );

    if (
        ua_rc != UA_STATUSCODE_GOOD
    ) {
        ESP_LOGE(
            TAG,
            "OPC UA setup/connect failed: %s",
            UA_StatusCode_name(ua_rc)
        );

        UA_Client_delete(client);
        return;
    }

    ESP_LOGI(
        TAG,
        "formal OPC UA %s persistent session ready",
        FAIR_OPCUA_PROFILE_NAME
    );

    err =
        fair_opcua_benchmark_run(
            &transport,
            &benchmark_config
        );

    if (
        err != ESP_OK
    ) {
        ESP_LOGE(
            TAG,
            "benchmark failed: %s",
            esp_err_to_name(err)
        );
    }

    UA_Client_disconnect(client);
    UA_Client_delete(client);
}
