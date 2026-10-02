#include "runtime_wifi.h"

#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#include "esp_event.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_random.h"
#include "esp_netif.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "nvs_flash.h"

#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"

#include "wifi_provisioning/manager.h"
#include "wifi_provisioning/scheme_softap.h"


static const char *TAG = "OCC_WIFI";

#define WIFI_CONNECTED_BIT BIT0

static EventGroupHandle_t s_wifi_event_group = NULL;


static void wifi_event_handler(
    void *arg,
    esp_event_base_t event_base,
    int32_t event_id,
    void *event_data
)
{
    (void)arg;

    if (event_base == WIFI_PROV_EVENT) {
        switch (event_id) {
            case WIFI_PROV_START:
                ESP_LOGI(
                    TAG,
                    "Wi-Fi provisioning started"
                );
                break;

            case WIFI_PROV_CRED_RECV: {
                /*
                 * Intentionally do NOT log the password.
                 */
                wifi_sta_config_t *wifi_cfg =
                    (wifi_sta_config_t *)event_data;

                ESP_LOGI(
                    TAG,
                    "Wi-Fi credentials received for SSID=%s",
                    (const char *)wifi_cfg->ssid
                );
                break;
            }

            case WIFI_PROV_CRED_FAIL:
                ESP_LOGW(
                    TAG,
                    "Wi-Fi provisioning credentials failed"
                );
                break;

            case WIFI_PROV_CRED_SUCCESS:
                ESP_LOGI(
                    TAG,
                    "Wi-Fi provisioning successful"
                );
                break;

            case WIFI_PROV_END:
                ESP_LOGI(
                    TAG,
                    "Wi-Fi provisioning finished"
                );

                wifi_prov_mgr_deinit();
                break;

            default:
                break;
        }

        return;
    }

    if (event_base == WIFI_EVENT) {
        switch (event_id) {
            case WIFI_EVENT_STA_START:
                ESP_LOGI(
                    TAG,
                    "Wi-Fi station started"
                );

                esp_wifi_connect();
                break;

            case WIFI_EVENT_STA_DISCONNECTED:
                xEventGroupClearBits(
                    s_wifi_event_group,
                    WIFI_CONNECTED_BIT
                );

                ESP_LOGW(
                    TAG,
                    "Wi-Fi disconnected; reconnecting"
                );

                esp_wifi_connect();
                break;

            default:
                break;
        }

        return;
    }

    if (
        event_base == IP_EVENT &&
        event_id == IP_EVENT_STA_GOT_IP
    ) {
        const ip_event_got_ip_t *event =
            (const ip_event_got_ip_t *)event_data;

        ESP_LOGI(
            TAG,
            "Wi-Fi connected IP=" IPSTR,
            IP2STR(&event->ip_info.ip)
        );

        xEventGroupSetBits(
            s_wifi_event_group,
            WIFI_CONNECTED_BIT
        );
    }
}


static esp_err_t initialise_nvs(void)
{
    esp_err_t err =
        nvs_flash_init();

    if (
        err == ESP_ERR_NVS_NO_FREE_PAGES ||
        err == ESP_ERR_NVS_NEW_VERSION_FOUND
    ) {
        err = nvs_flash_erase();

        if (err != ESP_OK) {
            return err;
        }

        err = nvs_flash_init();
    }

    return err;
}


static esp_err_t initialise_wifi_driver(void)
{
    esp_netif_t *sta =
        esp_netif_create_default_wifi_sta();

    if (sta == NULL) {
        return ESP_FAIL;
    }

    /*
     * SoftAP provisioning requires an AP netif as well.
     * The same firmware later switches to normal STA-only
     * operation after provisioning.
     */
    esp_netif_t *ap =
        esp_netif_create_default_wifi_ap();

    if (ap == NULL) {
        return ESP_FAIL;
    }

    wifi_init_config_t wifi_cfg =
        WIFI_INIT_CONFIG_DEFAULT();

    return esp_wifi_init(
        &wifi_cfg
    );
}


static esp_err_t start_saved_wifi(void)
{
    esp_err_t err =
        esp_wifi_set_mode(
            WIFI_MODE_STA
        );

    if (err != ESP_OK) {
        return err;
    }

    return esp_wifi_start();
}


static void build_provisioning_identity(
    char *service_name,
    size_t service_name_size,
    char *pop,
    size_t pop_size
)
{
    uint8_t mac[6] = {0};

    ESP_ERROR_CHECK(
        esp_read_mac(
            mac,
            ESP_MAC_WIFI_STA
        )
    );

    snprintf(
        service_name,
        service_name_size,
        "OCC-%02X%02X%02X",
        mac[3],
        mac[4],
        mac[5]
    );

    /*
     * Prototype setup secret.
     *
     * It is generated at runtime rather than compiled into
     * the firmware. For an industrial product this would
     * normally be factory-provisioned and supplied by a
     * QR label or equivalent secure onboarding process.
     */
    const uint32_t random_a =
        esp_random();

    const uint32_t random_b =
        esp_random();

    snprintf(
        pop,
        pop_size,
        "%08" PRIX32 "%08" PRIX32,
        random_a,
        random_b
    );
}


esp_err_t occ_runtime_wifi_connect_or_provision(void)
{
    esp_err_t err =
        initialise_nvs();

    if (err != ESP_OK) {
        return err;
    }

    err =
        esp_netif_init();

    if (err != ESP_OK) {
        return err;
    }

    err =
        esp_event_loop_create_default();

    if (err != ESP_OK) {
        return err;
    }

    s_wifi_event_group =
        xEventGroupCreate();

    if (s_wifi_event_group == NULL) {
        return ESP_ERR_NO_MEM;
    }

    ESP_ERROR_CHECK(
        esp_event_handler_register(
            WIFI_PROV_EVENT,
            ESP_EVENT_ANY_ID,
            wifi_event_handler,
            NULL
        )
    );

    ESP_ERROR_CHECK(
        esp_event_handler_register(
            WIFI_EVENT,
            ESP_EVENT_ANY_ID,
            wifi_event_handler,
            NULL
        )
    );

    ESP_ERROR_CHECK(
        esp_event_handler_register(
            IP_EVENT,
            IP_EVENT_STA_GOT_IP,
            wifi_event_handler,
            NULL
        )
    );

    /*
     * Wi-Fi must be initialized before asking the
     * provisioning manager whether credentials exist.
     */
    err =
        initialise_wifi_driver();

    if (err != ESP_OK) {
        ESP_LOGE(
            TAG,
            "Wi-Fi driver initialization failed: %s",
            esp_err_to_name(err)
        );

        return err;
    }

    ESP_LOGI(
        TAG,
        "Wi-Fi driver initialized"
    );

    wifi_prov_mgr_config_t prov_config = {
        .scheme =
            wifi_prov_scheme_softap,

        .scheme_event_handler =
            WIFI_PROV_EVENT_HANDLER_NONE,
    };

    err =
        wifi_prov_mgr_init(
            prov_config
        );

    if (err != ESP_OK) {
        return err;
    }

    bool provisioned = false;

    err =
        wifi_prov_mgr_is_provisioned(
            &provisioned
        );

    if (err != ESP_OK) {
        wifi_prov_mgr_deinit();
        return err;
    }

    if (!provisioned) {
        char service_name[20];
        char pop[20];

        build_provisioning_identity(
            service_name,
            sizeof(service_name),
            pop,
            sizeof(pop)
        );

        ESP_LOGW(
            TAG,
            "FIRST BOOT: Wi-Fi provisioning required"
        );

        ESP_LOGI(
            TAG,
            "Provisioning service=%s",
            service_name
        );

        ESP_LOGI(
            TAG,
            "Provisioning PoP=%s",
            pop
        );

        ESP_LOGI(
            TAG,
            "Provision using Espressif SoftAP provisioning"
        );

        err =
            wifi_prov_mgr_start_provisioning(
                WIFI_PROV_SECURITY_1,
                (const void *)pop,
                service_name,
                NULL
            );

        if (err != ESP_OK) {
            wifi_prov_mgr_deinit();
            return err;
        }
    } else {
        ESP_LOGI(
            TAG,
            "Saved Wi-Fi configuration found"
        );

        wifi_prov_mgr_deinit();

        err =
            start_saved_wifi();

        if (err != ESP_OK) {
            return err;
        }
    }

    ESP_LOGI(
        TAG,
        "Waiting for Wi-Fi connection"
    );

    xEventGroupWaitBits(
        s_wifi_event_group,
        WIFI_CONNECTED_BIT,
        pdFALSE,
        pdTRUE,
        portMAX_DELAY
    );

    ESP_LOGI(
        TAG,
        "Wi-Fi ready"
    );

    return ESP_OK;
}
