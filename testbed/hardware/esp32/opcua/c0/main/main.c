#include <stdlib.h>
#include <sys/time.h>
#include <time.h>
#include "esp_netif_sntp.h"
#include "opcua_client.h"
#include <stdio.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"

#include "esp_log.h"
#include "esp_event.h"
#include "esp_wifi.h"
#include "esp_netif.h"
#include "esp_system.h"
#include "nvs_flash.h"
#include "lwip/sockets.h"
#include "lwip/inet.h"
#include <errno.h>

#include "secrets.h"

static const char *TAG = "VEHICLE1_OPCUA";

#define WIFI_CONNECTED_BIT BIT0
#define WIFI_FAIL_BIT      BIT1
#define MAX_RETRY          10

static EventGroupHandle_t wifi_event_group;
static int retry_count = 0;

static void wifi_event_handler(
    void *arg,
    esp_event_base_t event_base,
    int32_t event_id,
    void *event_data)
{
    if (event_base == WIFI_EVENT &&
        event_id == WIFI_EVENT_STA_START) {

        ESP_LOGI(TAG, "Wi-Fi started, connecting...");
        esp_wifi_connect();
    }

    else if (event_base == WIFI_EVENT &&
             event_id == WIFI_EVENT_STA_DISCONNECTED) {

        if (retry_count < MAX_RETRY) {
            retry_count++;
            ESP_LOGW(
                TAG,
                "Wi-Fi disconnected. Retry %d/%d",
                retry_count,
                MAX_RETRY
            );

            esp_wifi_connect();
        } else {
            xEventGroupSetBits(
                wifi_event_group,
                WIFI_FAIL_BIT
            );
        }
    }

    else if (event_base == IP_EVENT &&
             event_id == IP_EVENT_STA_GOT_IP) {

        ip_event_got_ip_t *event =
            (ip_event_got_ip_t *) event_data;

        ESP_LOGI(
            TAG,
            "Wi-Fi connected"
        );

        ESP_LOGI(
            TAG,
            "ESP32 IP: " IPSTR,
            IP2STR(&event->ip_info.ip)
        );

        ESP_LOGI(
            TAG,
            "Gateway: " IPSTR,
            IP2STR(&event->ip_info.gw)
        );

        retry_count = 0;

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

    esp_event_handler_instance_t instance_any_id;
    esp_event_handler_instance_t instance_got_ip;

    ESP_ERROR_CHECK(
        esp_event_handler_instance_register(
            WIFI_EVENT,
            ESP_EVENT_ANY_ID,
            &wifi_event_handler,
            NULL,
            &instance_any_id
        )
    );

    ESP_ERROR_CHECK(
        esp_event_handler_instance_register(
            IP_EVENT,
            IP_EVENT_STA_GOT_IP,
            &wifi_event_handler,
            NULL,
            &instance_got_ip
        )
    );

    wifi_config_t wifi_config = {0};

    strncpy(
        (char *)wifi_config.sta.ssid,
        WIFI_SSID,
        sizeof(wifi_config.sta.ssid) - 1
    );

    strncpy(
        (char *)wifi_config.sta.password,
        WIFI_PASSWORD,
        sizeof(wifi_config.sta.password) - 1
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

    ESP_LOGI(
        TAG,
        "Waiting for Wi-Fi connection..."
    );

    EventBits_t bits =
        xEventGroupWaitBits(
            wifi_event_group,
            WIFI_CONNECTED_BIT |
            WIFI_FAIL_BIT,
            pdFALSE,
            pdFALSE,
            portMAX_DELAY
        );

    if (bits & WIFI_CONNECTED_BIT) {
        ESP_LOGI(
            TAG,
            "Vehicle 1 network ready"
        );
    }

    else if (bits & WIFI_FAIL_BIT) {
        ESP_LOGE(
            TAG,
            "Unable to connect to Wi-Fi"
        );
    }
}



static void sync_system_time(void)
{
    const char *time_server_ip = "192.168.1.115";
    const int time_server_port = 5555;

    ESP_LOGI(TAG, "Synchronizing clock from OCC Raspberry Pi");

    int sock = socket(AF_INET, SOCK_STREAM, IPPROTO_IP);

    if (sock < 0) {
        ESP_LOGE(TAG, "Unable to create time sync socket");
        return;
    }

    struct sockaddr_in dest = {0};
    dest.sin_family = AF_INET;
    dest.sin_port = htons(time_server_port);

    if (inet_pton(AF_INET, time_server_ip, &dest.sin_addr) != 1) {
        ESP_LOGE(TAG, "Invalid time server IP");
        close(sock);
        return;
    }

    if (connect(sock, (struct sockaddr *)&dest, sizeof(dest)) != 0) {
        ESP_LOGE(TAG, "Unable to connect to OCC time server");
        close(sock);
        return;
    }

    char buffer[64] = {0};

    int len = recv(sock, buffer, sizeof(buffer) - 1, 0);

    close(sock);

    if (len <= 0) {
        ESP_LOGE(TAG, "No time received from OCC");
        return;
    }

    buffer[len] = '\0';

    unsigned long long epoch_ms = strtoull(buffer, NULL, 10);

    struct timeval tv = {
        .tv_sec = epoch_ms / 1000ULL,
        .tv_usec = (epoch_ms % 1000ULL) * 1000ULL
    };

    if (settimeofday(&tv, NULL) != 0) {
        ESP_LOGE(TAG, "settimeofday failed");
        return;
    }

    time_t now;
    time(&now);

    ESP_LOGI(
        TAG,
        "OCC time synchronized successfully, epoch=%lld",
        (long long)now
    );
}

static void test_occ_reachability(void)
{
    const char *occ_ip = "192.168.1.115";
    const int occ_port = 22;

    int sock = socket(AF_INET, SOCK_STREAM, IPPROTO_IP);

    if (sock < 0) {
        ESP_LOGE(TAG, "Unable to create OCC test socket");
        return;
    }

    struct timeval timeout = {
        .tv_sec = 3,
        .tv_usec = 0
    };

    setsockopt(
        sock,
        SOL_SOCKET,
        SO_RCVTIMEO,
        &timeout,
        sizeof(timeout)
    );

    setsockopt(
        sock,
        SOL_SOCKET,
        SO_SNDTIMEO,
        &timeout,
        sizeof(timeout)
    );

    struct sockaddr_in dest = {0};

    dest.sin_family = AF_INET;
    dest.sin_port = htons(occ_port);
    inet_pton(AF_INET, occ_ip, &dest.sin_addr);

    ESP_LOGI(
        TAG,
        "Testing Raspberry Pi OCC %s:%d",
        occ_ip,
        occ_port
    );

    int err = connect(
        sock,
        (struct sockaddr *)&dest,
        sizeof(dest)
    );

    if (err == 0) {
        ESP_LOGI(
            TAG,
            "OCC REACHABILITY PASS: Raspberry Pi reachable"
        );
    } else {
        ESP_LOGE(
            TAG,
            "OCC REACHABILITY FAIL: errno=%d",
            errno
        );
    }

    close(sock);
}

void app_main(void)
{
    ESP_LOGI(
        TAG,
        "Vehicle 1 OPC UA firmware starting"
    );

    esp_err_t ret = nvs_flash_init();

    if (ret == ESP_ERR_NVS_NO_FREE_PAGES ||
        ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {

        ESP_ERROR_CHECK(
            nvs_flash_erase()
        );

        ESP_ERROR_CHECK(
            nvs_flash_init()
        );
    }

    wifi_init();

    sync_system_time();

    ESP_LOGI(
        TAG,
        "Next target: Raspberry Pi OCC 192.168.1.115"
    );

    test_occ_reachability();

    ESP_LOGI(TAG, "Starting OPC UA C0 hardware test");
    opcua_c0_test();

    while (1) {

        ESP_LOGI(
            TAG,
            "Vehicle 1 alive - Wi-Fi operational"
        );

        vTaskDelay(
            pdMS_TO_TICKS(5000)
        );
    }
}
