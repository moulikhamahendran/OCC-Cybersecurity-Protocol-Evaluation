#include <stdio.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"

#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "nvs_flash.h"

#include "lwip/inet.h"
#include "lwip/sockets.h"

#include "secrets.h"

#define PI_IP              "192.168.1.115"
#define PI_PORT            5055
#define SAMPLE_RATE_HZ     10
#define SAMPLE_PERIOD_MS   (1000 / SAMPLE_RATE_HZ)
#define TOTAL_SAMPLES      600

static const char *TAG = "DDS_FEEDER";

static EventGroupHandle_t wifi_event_group;
#define WIFI_CONNECTED_BIT BIT0


static void wifi_event_handler(
    void *arg,
    esp_event_base_t event_base,
    int32_t event_id,
    void *event_data)
{
    if (
        event_base == WIFI_EVENT &&
        event_id == WIFI_EVENT_STA_START
    ) {
        esp_wifi_connect();
    }

    else if (
        event_base == WIFI_EVENT &&
        event_id == WIFI_EVENT_STA_DISCONNECTED
    ) {
        ESP_LOGW(TAG, "Wi-Fi disconnected, reconnecting...");
        esp_wifi_connect();
    }

    else if (
        event_base == IP_EVENT &&
        event_id == IP_EVENT_STA_GOT_IP
    ) {
        ip_event_got_ip_t *event =
            (ip_event_got_ip_t *)event_data;

        ESP_LOGI(
            TAG,
            "Wi-Fi connected, IP=" IPSTR,
            IP2STR(&event->ip_info.ip)
        );

        xEventGroupSetBits(
            wifi_event_group,
            WIFI_CONNECTED_BIT
        );
    }
}


static void wifi_init(void)
{
    wifi_event_group = xEventGroupCreate();

    ESP_ERROR_CHECK(
        esp_netif_init()
    );

    ESP_ERROR_CHECK(
        esp_event_loop_create_default()
    );

    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg =
        WIFI_INIT_CONFIG_DEFAULT();

    ESP_ERROR_CHECK(
        esp_wifi_init(&cfg)
    );

    ESP_ERROR_CHECK(
        esp_event_handler_register(
            WIFI_EVENT,
            ESP_EVENT_ANY_ID,
            &wifi_event_handler,
            NULL
        )
    );

    ESP_ERROR_CHECK(
        esp_event_handler_register(
            IP_EVENT,
            IP_EVENT_STA_GOT_IP,
            &wifi_event_handler,
            NULL
        )
    );

    wifi_config_t wifi_config = {0};

    snprintf(
        (char *)wifi_config.sta.ssid,
        sizeof(wifi_config.sta.ssid),
        "%s",
        WIFI_SSID
    );

    snprintf(
        (char *)wifi_config.sta.password,
        sizeof(wifi_config.sta.password),
        "%s",
        WIFI_PASSWORD
    );

    ESP_ERROR_CHECK(
        esp_wifi_set_mode(WIFI_MODE_STA)
    );

    ESP_ERROR_CHECK(
        esp_wifi_set_config(
            WIFI_IF_STA,
            &wifi_config
        )
    );

    ESP_ERROR_CHECK(
        esp_wifi_start()
    );

    ESP_LOGI(TAG, "Waiting for Wi-Fi...");

    xEventGroupWaitBits(
        wifi_event_group,
        WIFI_CONNECTED_BIT,
        pdFALSE,
        pdTRUE,
        portMAX_DELAY
    );
}


static void send_dds_feeder_samples(void)
{
    int sock = socket(
        AF_INET,
        SOCK_DGRAM,
        IPPROTO_IP
    );

    if (sock < 0) {
        ESP_LOGE(TAG, "Unable to create UDP socket");
        return;
    }

    struct sockaddr_in destination = {
        .sin_family = AF_INET,
        .sin_port = htons(PI_PORT),
    };

    destination.sin_addr.s_addr =
        inet_addr(PI_IP);

    ESP_LOGI(TAG, "====================================");
    ESP_LOGI(TAG, "ESP32 DDS HARDWARE FEEDER");
    ESP_LOGI(TAG, "Target: %s:%d", PI_IP, PI_PORT);
    ESP_LOGI(TAG, "Rate: %d Hz", SAMPLE_RATE_HZ);
    ESP_LOGI(TAG, "Samples: %d", TOTAL_SAMPLES);
    ESP_LOGI(TAG, "====================================");

    for (
        uint32_t sequence = 0;
        sequence < TOTAL_SAMPLES;
        sequence++
    ) {
        char payload[512];

        double x =
            1.0 + ((double)sequence * 0.01);

        double y =
            2.0;

        double theta =
            0.5;

        int length = snprintf(
            payload,
            sizeof(payload),
            "{"
                "\"headerId\":%lu,"
                "\"serialNumber\":\"VM-001\","
                "\"agvPosition\":{"
                    "\"x\":%.3f,"
                    "\"y\":%.3f,"
                    "\"theta\":%.3f,"
                    "\"mapId\":\"OCC-LAB\""
                "}"
            "}",
            (unsigned long)sequence,
            x,
            y,
            theta
        );

        if (
            length <= 0 ||
            length >= sizeof(payload)
        ) {
            ESP_LOGE(
                TAG,
                "Payload generation failed"
            );
            continue;
        }

        int sent = sendto(
            sock,
            payload,
            length,
            0,
            (struct sockaddr *)&destination,
            sizeof(destination)
        );

        if (sent < 0) {
            ESP_LOGE(
                TAG,
                "SEND FAIL headerId=%lu",
                (unsigned long)sequence
            );
        } else {
            ESP_LOGI(
                TAG,
                "SEND | headerId=%lu | bytes=%d",
                (unsigned long)sequence,
                sent
            );
        }

        vTaskDelay(
            pdMS_TO_TICKS(SAMPLE_PERIOD_MS)
        );
    }

    ESP_LOGI(
        TAG,
        "DDS feeder smoke campaign finished"
    );

    close(sock);
}


void app_main(void)
{
    esp_err_t ret =
        nvs_flash_init();

    if (
        ret == ESP_ERR_NVS_NO_FREE_PAGES ||
        ret == ESP_ERR_NVS_NEW_VERSION_FOUND
    ) {
        ESP_ERROR_CHECK(
            nvs_flash_erase()
        );

        ESP_ERROR_CHECK(
            nvs_flash_init()
        );
    }

    wifi_init();

    vTaskDelay(
        pdMS_TO_TICKS(1000)
    );

    send_dds_feeder_samples();
}
