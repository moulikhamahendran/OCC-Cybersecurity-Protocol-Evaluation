#include "opcua_c0_runtime.h"

#include "esp_netif_sntp.h"
#include "sdkconfig.h"
#include <time.h>
#include <string.h>

#include "opcua_c0_adapter.h"
#include "vehicle_state.h"

#include <stdbool.h>
#include <stdint.h>
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "occ_opcua_c0";
static occ_opcua_c0_adapter_t s_adapter;


/* OCC_OPCUA_SNTP_REPAIR_V1 */
static bool occ_opcua_clock_valid(void)
{
    return time(NULL) >= (time_t)1700000000;
}

/* OCC_OPCUA_SNTP_CONTROLLED_START_V1 */
static bool occ_opcua_ntp_host(const char *endpoint, char *host, size_t capacity)
{
    const char *start = strstr(endpoint, "://");
    start = start ? start + 3 : endpoint;
    const char *end;
    if (*start == '[') {
        ++start;
        end = strchr(start, ']');
        if (!end) return false;
    } else {
        end = start + strcspn(start, ":/");
    }
    size_t length = (size_t)(end - start);
    if (!length || length >= capacity) return false;
    memcpy(host, start, length);
    host[length] = '\0';
    return true;
}

static bool occ_opcua_ensure_clock(occ_security_t security, const char *endpoint)
{
    if (occ_opcua_clock_valid()) {
        return true;
    }

    char local_host[256];
    if (!occ_opcua_ntp_host(endpoint, local_host, sizeof(local_host))) return false;

    const char *servers[] = {
        CONFIG_OCC_OPCUA_LOCAL_NTP_SERVER[0] ?
            CONFIG_OCC_OPCUA_LOCAL_NTP_SERVER : local_host,
        CONFIG_OCC_SNTP_PRIMARY_SERVER,
        "time.google.com"
    };

    const uint32_t wait_ms =
        security == OCC_SECURITY_C0 ? 12000U : 30000U;

    for (size_t i = 0; i < sizeof(servers) / sizeof(servers[0]); ++i) {
        if (!servers[i] || !servers[i][0]) continue;
        bool duplicate = false;
        for (size_t j = 0; j < i; ++j)
            if (servers[j] && strcmp(servers[j], servers[i]) == 0) duplicate = true;
        if (duplicate) continue;
        ESP_LOGI(TAG, "SNTP init server=%s", servers[i]);

        esp_sntp_config_t config =
            ESP_NETIF_SNTP_DEFAULT_CONFIG(servers[i]);

        config.start = false;

        esp_err_t err = esp_netif_sntp_init(&config);

        if (err != ESP_OK) {
            ESP_LOGE(TAG, "SNTP init error=%s",
                     esp_err_to_name(err));
            continue;
        }

        err = esp_netif_sntp_start();

        if (err == ESP_OK) {
            ESP_LOGI(TAG, "SNTP started server=%s", servers[i]);

            err = esp_netif_sntp_sync_wait(
                pdMS_TO_TICKS(wait_ms));
        }

        bool clock_ok = occ_opcua_clock_valid();

        ESP_LOGI(TAG,
                 "SNTP result server=%s status=%s "
                 "clock_valid=%d epoch=%lld",
                 servers[i],
                 esp_err_to_name(err),
                 (int)clock_ok,
                 (long long)time(NULL));

        esp_netif_sntp_deinit();

        if (err == ESP_OK && clock_ok) {
            time_t now = time(NULL);
            struct tm utc;
            char date[32];
            gmtime_r(&now, &utc);
            strftime(date, sizeof(date), "%Y-%m-%dT%H:%M:%SZ", &utc);
            ESP_LOGI(TAG, "OPC UA clock synchronized clock_valid=1 utc=%s server=%s", date, servers[i]);
            return true;
        }
    }

    ESP_LOGW(TAG, "OPC UA clock remains unsynchronized");
    return false;
}

/* C0 must continue telemetry while time sources are temporarily unavailable. */
static void occ_opcua_clock_task(void *arg)
{
    const char *endpoint = arg;
    for (;;) {
        occ_opcua_ensure_clock(OCC_SECURITY_C0, endpoint);
        vTaskDelay(pdMS_TO_TICKS(60000));
    }
}

esp_err_t occ_opcua_run(const char *vehicle_id, const char *endpoint,
                        occ_security_t security)
{
    if (!vehicle_id || !vehicle_id[0] || !endpoint || !endpoint[0] ||
        security < OCC_SECURITY_C0 || security > OCC_SECURITY_C2)
        return ESP_ERR_INVALID_ARG;

    /* Copy the host: the task must not retain a caller-owned pointer. */
    static char clock_endpoint[256];
    static TaskHandle_t clock_task;
    if (security == OCC_SECURITY_C0 && !clock_task) {
        if (strlen(endpoint) >= sizeof(clock_endpoint)) return ESP_ERR_INVALID_ARG;
        strcpy(clock_endpoint, endpoint);
        if (xTaskCreate(occ_opcua_clock_task, "opcua_time", 4096,
                        clock_endpoint, 3, &clock_task) != pdPASS)
            return ESP_ERR_NO_MEM;
    }

    bool have_last_sent = false;
    uint32_t last_sent = 0U;

    for (;;) {
        if (security != OCC_SECURITY_C0 &&
            !occ_opcua_ensure_clock(security, endpoint)) {
            ESP_LOGW(TAG,
                     "Secure OPC UA requires a valid clock; retrying");
            vTaskDelay(pdMS_TO_TICKS(5000));
            continue;
        }

        if (!occ_opcua_profile_init(&s_adapter, endpoint, vehicle_id, security)) {
            ESP_LOGE(TAG, "OPC UA adapter setup rejected");
            return ESP_ERR_INVALID_ARG;
        }

        UA_StatusCode rc = occ_opcua_c0_start(&s_adapter);
        if (rc == UA_STATUSCODE_GOOD) {
            ESP_LOGI(TAG, "OPC UA C%d connected", (int)security);
            while (occ_opcua_c0_ready(&s_adapter)) {
                vehicle_state_t state;
                if (!vehicle_state_get(&state) || state.seq == 0U ||
                    (have_last_sent && state.seq == last_sent)) {
                    vTaskDelay(pdMS_TO_TICKS(100));
                    continue;
                }

                rc = occ_opcua_c0_send_snapshot(&s_adapter, 5000U);
                if (rc != UA_STATUSCODE_GOOD) {
                    ESP_LOGW(TAG, "Telemetry/ack failed: 0x%08lx",
                             (unsigned long)rc);
                    break;
                }
                last_sent = state.seq;
                have_last_sent = true;
                vTaskDelay(pdMS_TO_TICKS(100));
            }
        } else {
            ESP_LOGW(TAG, "Connect failed: 0x%08lx", (unsigned long)rc);
        }

        /* A failed async request must not reuse its original client. */
        occ_opcua_c0_stop(&s_adapter);
        ESP_LOGW(TAG, "OPC UA session stopped; retrying after 3s");
        vTaskDelay(pdMS_TO_TICKS(3000));
    }
}

/* Backwards-compatible C0 API. */
esp_err_t occ_opcua_c0_run(const char *vehicle_id, const char *endpoint) {
    return occ_opcua_run(vehicle_id, endpoint, OCC_SECURITY_C0);
}
