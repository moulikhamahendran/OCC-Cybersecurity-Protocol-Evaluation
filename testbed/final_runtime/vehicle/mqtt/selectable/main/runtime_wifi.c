#include "runtime_wifi.h"
#include "runtime_mqtt_config.h"
#include "runtime_endpoint_config.h"
#include "runtime_known_wifi.h"

#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "esp_event.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_random.h"
#include "esp_netif.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "nvs_flash.h"
#include "cJSON.h"

#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"

#include "wifi_provisioning/manager.h"
#include "wifi_provisioning/scheme_softap.h"


static const char *TAG = "OCC_WIFI";

#define WIFI_CONNECTED_BIT BIT0

static EventGroupHandle_t s_wifi_event_group = NULL;

static bool s_wifi_credentials_ready = false;
static bool s_mqtt_credentials_ready = false;
static bool s_occ_endpoint_ready = false;


static esp_err_t mqtt_credentials_prov_handler(
    uint32_t session_id,
    const uint8_t *inbuf,
    ssize_t inlen,
    uint8_t **outbuf,
    ssize_t *outlen,
    void *priv_data
)
{
    (void)session_id;
    (void)priv_data;

    const char *response = "ERROR";

    if (
        inbuf != NULL &&
        inlen > 0 &&
        outbuf != NULL &&
        outlen != NULL
    ) {
        cJSON *root =
            cJSON_ParseWithLength(
                (const char *)inbuf,
                (size_t)inlen
            );

        if (root != NULL) {
            const cJSON *username =
                cJSON_GetObjectItemCaseSensitive(
                    root,
                    "username"
                );

            const cJSON *password =
                cJSON_GetObjectItemCaseSensitive(
                    root,
                    "password"
                );

            const cJSON *occ_host =
                cJSON_GetObjectItemCaseSensitive(
                    root,
                    "occ_host"
                );

            const bool credentials_valid =
                cJSON_IsString(username) &&
                username->valuestring != NULL &&
                cJSON_IsString(password) &&
                password->valuestring != NULL;

            const bool endpoint_valid =
                cJSON_IsString(occ_host) &&
                occ_host->valuestring != NULL &&
                occ_endpoint_host_is_valid(
                    occ_host->valuestring
                );

            if (
                credentials_valid &&
                endpoint_valid
            ) {
                esp_err_t credentials_err =
                    occ_mqtt_credentials_save(
                        username->valuestring,
                        password->valuestring
                    );

                esp_err_t endpoint_err =
                    occ_endpoint_host_save(
                        occ_host->valuestring
                    );

                if (
                    credentials_err == ESP_OK &&
                    endpoint_err == ESP_OK
                ) {
                    ESP_LOGI(
                        TAG,
                        "MQTT credentials and OCC endpoint stored in NVS"
                    );

                    ESP_LOGI(
                        TAG,
                        "Provisioned OCC endpoint=%s",
                        occ_host->valuestring
                    );

                    s_mqtt_credentials_ready = true;
                    s_occ_endpoint_ready = true;
                    response = "SUCCESS";

                    if (s_wifi_credentials_ready) {
                        wifi_prov_mgr_stop_provisioning();
                    }
                } else {
                    if (credentials_err != ESP_OK) {
                        ESP_LOGE(
                            TAG,
                            "MQTT credential storage failed: %s",
                            esp_err_to_name(
                                credentials_err
                            )
                        );
                    }

                    if (endpoint_err != ESP_OK) {
                        ESP_LOGE(
                            TAG,
                            "OCC endpoint storage failed: %s",
                            esp_err_to_name(
                                endpoint_err
                            )
                        );
                    }
                }
            } else {
                ESP_LOGW(
                    TAG,
                    "Provisioning custom-data requires username, password and valid occ_host"
                );
            }

            cJSON_Delete(root);
        }
    }

    size_t response_len =
        strlen(response) + 1U;

    *outbuf =
        malloc(response_len);

    if (*outbuf == NULL) {
        return ESP_ERR_NO_MEM;
    }

    memcpy(
        *outbuf,
        response,
        response_len
    );

    *outlen =
        (ssize_t)response_len;

    return ESP_OK;
}


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

                s_wifi_credentials_ready = true;

                if (
                    s_mqtt_credentials_ready &&
                    s_occ_endpoint_ready
                ) {
                    wifi_prov_mgr_stop_provisioning();
                }

                break;

            case WIFI_PROV_END:
                ESP_LOGI(
                    TAG,
                    "Wi-Fi provisioning finished"
                );

                wifi_prov_mgr_deinit();

                if (
                    s_wifi_credentials_ready &&
                    s_mqtt_credentials_ready &&
                    s_occ_endpoint_ready
                ) {
                    ESP_LOGI(
                        TAG,
                        "Runtime provisioning complete; restarting"
                    );

                    esp_restart();
                }

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

                if (
                    occ_known_wifi_rotate_after_disconnect()
                ) {
                    ESP_LOGW(
                        TAG,
                        "Known-network rotation selected"
                    );
                }

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

        occ_known_wifi_connected();

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

    if (
        occ_known_wifi_consume_reprovision_request()
    ) {
        ESP_LOGW(
            TAG,
            "Controlled Wi-Fi reprovisioning requested"
        );

        err =
            wifi_prov_mgr_reset_provisioning();

        if (err != ESP_OK) {
            wifi_prov_mgr_deinit();

            ESP_LOGE(
                TAG,
                "Wi-Fi provisioning reset failed: %s",
                esp_err_to_name(err)
            );

            return err;
        }
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

    occ_mqtt_credentials_t existing_credentials;

    esp_err_t mqtt_credentials_err =
        occ_mqtt_credentials_load(
            &existing_credentials
        );

    bool mqtt_credentials_present =
        mqtt_credentials_err == ESP_OK;

    memset(
        &existing_credentials,
        0,
        sizeof(existing_credentials)
    );

    char existing_occ_host[
        OCC_ENDPOINT_HOST_MAX_LEN
    ] = {0};

    esp_err_t occ_endpoint_err =
        occ_endpoint_host_load(
            existing_occ_host,
            sizeof(existing_occ_host)
        );

    bool occ_endpoint_present =
        occ_endpoint_err == ESP_OK;

    memset(
        existing_occ_host,
        0,
        sizeof(existing_occ_host)
    );

    s_wifi_credentials_ready =
        provisioned;

    s_mqtt_credentials_ready =
        mqtt_credentials_present;

    s_occ_endpoint_ready =
        occ_endpoint_present;

    if (
        !provisioned ||
        !mqtt_credentials_present ||
        !occ_endpoint_present
    ) {
        char service_name[20];
        char pop[20];

        build_provisioning_identity(
            service_name,
            sizeof(service_name),
            pop,
            sizeof(pop)
        );

        if (!provisioned) {
            ESP_LOGW(
                TAG,
                "FIRST BOOT: Wi-Fi, MQTT and OCC endpoint provisioning required"
            );
        } else if (
            !mqtt_credentials_present &&
            !occ_endpoint_present
        ) {
            ESP_LOGW(
                TAG,
                "MQTT credentials and OCC endpoint missing; provisioning required"
            );
        } else if (!mqtt_credentials_present) {
            ESP_LOGW(
                TAG,
                "MQTT credentials missing; provisioning required"
            );
        } else {
            ESP_LOGW(
                TAG,
                "OCC endpoint missing; provisioning required"
            );
        }

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
            wifi_prov_mgr_endpoint_create(
                "custom-data"
            );

        if (err != ESP_OK) {
            wifi_prov_mgr_deinit();
            return err;
        }

        err =
            wifi_prov_mgr_disable_auto_stop(
                1000
            );

        if (err != ESP_OK) {
            wifi_prov_mgr_deinit();
            return err;
        }

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

        err =
            wifi_prov_mgr_endpoint_register(
                "custom-data",
                mqtt_credentials_prov_handler,
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
