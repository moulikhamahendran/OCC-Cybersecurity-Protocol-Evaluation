#include <stdio.h>
#include <string.h>

#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_netif_sntp.h"
#include "esp_wifi.h"
#include "nvs_flash.h"

#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"

#include "fair_opcua_network.h"

static const char *TAG =
    "FAIR_OPCUA_NET";

static EventGroupHandle_t
    s_wifi_events;

static const EventBits_t
    FAIR_WIFI_CONNECTED_BIT =
        BIT0;

static void fair_wifi_event_handler(
    void *arg,
    esp_event_base_t base,
    int32_t id,
    void *data
)
{
    (void)arg;
    (void)data;

    if (
        base == WIFI_EVENT &&
        id == WIFI_EVENT_STA_START
    ) {
        esp_wifi_connect();
        return;
    }

    if (
        base == WIFI_EVENT &&
        id == WIFI_EVENT_STA_DISCONNECTED
    ) {
        if (
            s_wifi_events != NULL
        ) {
            xEventGroupClearBits(
                s_wifi_events,
                FAIR_WIFI_CONNECTED_BIT
            );
        }

        esp_wifi_connect();
        return;
    }

    if (
        base == IP_EVENT &&
        id == IP_EVENT_STA_GOT_IP
    ) {
        if (
            s_wifi_events != NULL
        ) {
            xEventGroupSetBits(
                s_wifi_events,
                FAIR_WIFI_CONNECTED_BIT
            );
        }
    }
}

esp_err_t fair_opcua_network_connect(
    const char *ssid,
    const char *password,
    TickType_t timeout_ticks
)
{
    if (
        ssid == NULL ||
        ssid[0] == '\0' ||
        password == NULL
    ) {
        return ESP_ERR_INVALID_ARG;
    }

    esp_err_t err =
        nvs_flash_init();

    if (
        err == ESP_ERR_NVS_NO_FREE_PAGES ||
        err == ESP_ERR_NVS_NEW_VERSION_FOUND
    ) {
        ESP_ERROR_CHECK(
            nvs_flash_erase()
        );

        err =
            nvs_flash_init();
    }

    if (
        err != ESP_OK
    ) {
        return err;
    }

    err =
        esp_netif_init();

    if (
        err != ESP_OK &&
        err != ESP_ERR_INVALID_STATE
    ) {
        return err;
    }

    err =
        esp_event_loop_create_default();

    if (
        err != ESP_OK &&
        err != ESP_ERR_INVALID_STATE
    ) {
        return err;
    }

    if (
        esp_netif_create_default_wifi_sta() ==
        NULL
    ) {
        return ESP_FAIL;
    }

    wifi_init_config_t init_config =
        WIFI_INIT_CONFIG_DEFAULT();

    err =
        esp_wifi_init(
            &init_config
        );

    if (
        err != ESP_OK
    ) {
        return err;
    }

    s_wifi_events =
        xEventGroupCreate();

    if (
        s_wifi_events == NULL
    ) {
        return ESP_ERR_NO_MEM;
    }

    err =
        esp_event_handler_register(
            WIFI_EVENT,
            ESP_EVENT_ANY_ID,
            fair_wifi_event_handler,
            NULL
        );

    if (
        err != ESP_OK
    ) {
        return err;
    }

    err =
        esp_event_handler_register(
            IP_EVENT,
            IP_EVENT_STA_GOT_IP,
            fair_wifi_event_handler,
            NULL
        );

    if (
        err != ESP_OK
    ) {
        return err;
    }

    wifi_config_t wifi_config = {0};

    snprintf(
        (char *)wifi_config.sta.ssid,
        sizeof(
            wifi_config.sta.ssid
        ),
        "%s",
        ssid
    );

    snprintf(
        (char *)wifi_config.sta.password,
        sizeof(
            wifi_config.sta.password
        ),
        "%s",
        password
    );

    err =
        esp_wifi_set_mode(
            WIFI_MODE_STA
        );

    if (
        err != ESP_OK
    ) {
        return err;
    }

    err =
        esp_wifi_set_config(
            WIFI_IF_STA,
            &wifi_config
        );

    if (
        err != ESP_OK
    ) {
        return err;
    }

    /*
     * Frozen network-control requirement:
     * Wi-Fi power save disabled.
     */
    err =
        esp_wifi_set_ps(
            WIFI_PS_NONE
        );

    if (
        err != ESP_OK
    ) {
        return err;
    }

    err =
        esp_wifi_start();

    if (
        err != ESP_OK
    ) {
        return err;
    }

    const EventBits_t bits =
        xEventGroupWaitBits(
            s_wifi_events,
            FAIR_WIFI_CONNECTED_BIT,
            pdFALSE,
            pdTRUE,
            timeout_ticks
        );

    if (
        (
            bits &
            FAIR_WIFI_CONNECTED_BIT
        ) == 0
    ) {
        ESP_LOGE(
            TAG,
            "Wi-Fi connection timeout"
        );

        return ESP_ERR_TIMEOUT;
    }

    ESP_LOGI(
        TAG,
        "Wi-Fi connected; power save disabled"
    );

    return ESP_OK;
}

esp_err_t fair_opcua_network_sync_time(
    const char *sntp_server,
    TickType_t timeout_ticks
)
{
    if (
        sntp_server == NULL ||
        sntp_server[0] == '\0'
    ) {
        return ESP_ERR_INVALID_ARG;
    }

    esp_sntp_config_t config =
        ESP_NETIF_SNTP_DEFAULT_CONFIG(
            sntp_server
        );

    esp_err_t err =
        esp_netif_sntp_init(
            &config
        );

    if (
        err != ESP_OK
    ) {
        return err;
    }

    err =
        esp_netif_sntp_sync_wait(
            timeout_ticks
        );

    esp_netif_sntp_deinit();

    return err;
}
