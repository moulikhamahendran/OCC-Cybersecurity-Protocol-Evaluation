#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "esp_err.h"
#include "esp_log.h"
#include "nvs.h"
#include "driver/uart.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define OCC_OPCUA_UART UART_NUM_0
#define OCC_OPCUA_LINE_MAX 300
#define OCC_OPCUA_WAIT_MS 20000

static const char *TAG = "OPCUA_PROVISION";

static void secure_wipe(void *buf, size_t len)
{
    volatile unsigned char *p = (volatile unsigned char *)buf;
    while (len--) {
        *p++ = 0;
    }
}

esp_err_t occ_opcua_provision_boot(void)
{
    nvs_handle_t nvs;
    esp_err_t rc = nvs_open("occ_opcua", NVS_READONLY, &nvs);

    if (rc == ESP_OK) {
        size_t user_size = 0;
        size_t pass_size = 0;

        esp_err_t u = nvs_get_str(nvs, "username", NULL, &user_size);
        esp_err_t p = nvs_get_str(nvs, "password", NULL, &pass_size);

        nvs_close(nvs);

        if (u == ESP_OK && p == ESP_OK &&
            user_size > 1 && pass_size > 1) {
            ESP_LOGI(TAG, "Dedicated OPC UA credentials present");
            return ESP_OK;
        }

        if (u != ESP_ERR_NVS_NOT_FOUND ||
            p != ESP_ERR_NVS_NOT_FOUND) {
            ESP_LOGE(TAG, "Incomplete OPC UA credential record");
            return ESP_ERR_INVALID_STATE;
        }
    } else if (rc != ESP_ERR_NVS_NOT_FOUND) {
        ESP_LOGE(TAG, "Cannot inspect OPC UA NVS namespace");
        return rc;
    }

    rc = uart_driver_install(
        OCC_OPCUA_UART, 1024, 0, 0, NULL, 0
    );

    bool owns_driver = (rc == ESP_OK);

    if (rc != ESP_OK && rc != ESP_ERR_INVALID_STATE) {
        ESP_LOGE(TAG, "UART provisioning unavailable");
        return rc;
    }

    uart_flush_input(OCC_OPCUA_UART);

    /* No completed request must never be reported as success. */
    rc = ESP_ERR_TIMEOUT;

    ESP_LOGW(TAG,
        "OPCUA_PROVISION_READY window_ms=%u",
        (unsigned)OCC_OPCUA_WAIT_MS);

    ESP_LOGW(TAG,
        "Local USB serial only; credentials will not be logged");

    char line[OCC_OPCUA_LINE_MAX] = {0};
    size_t used = 0;
    bool complete = false;

    TickType_t deadline =
        xTaskGetTickCount() + pdMS_TO_TICKS(OCC_OPCUA_WAIT_MS);

    while ((int32_t)(deadline - xTaskGetTickCount()) > 0) {
        uint8_t ch = 0;
        int received = uart_read_bytes(
            OCC_OPCUA_UART, &ch, 1, pdMS_TO_TICKS(100)
        );

        if (received <= 0) {
            continue;
        }

        if (ch == '\r') {
            continue;
        }

        if (ch == '\n') {
            complete = true;
            break;
        }

        /* Only printable ASCII is accepted in this lab command. */
        if (ch < 0x20 || ch > 0x7e) {
            ESP_LOGE(TAG, "Non-printable provisioning input");
            rc = ESP_ERR_INVALID_ARG;
            goto cleanup;
        }

        if (used + 1 >= sizeof(line)) {
            ESP_LOGE(TAG, "Credential input too long");
            rc = ESP_ERR_INVALID_ARG;
            goto cleanup;
        }

        line[used++] = (char)ch;
    }

    if (!complete) {
        ESP_LOGW(TAG, "No OPC UA provisioning request received");
        goto cleanup;
    }

    line[used] = '\0';

    if (strncmp(line, "OPCUA1|", 7) != 0) {
        ESP_LOGE(TAG, "Invalid provisioning command");
        goto cleanup;
    }

    char *username = line + 7;
    char *separator = strchr(username, '|');

    if (!separator) {
        ESP_LOGE(TAG, "Invalid provisioning fields");
        goto cleanup;
    }

    *separator = '\0';
    char *password = separator + 1;

    if (!username[0] ||
        strlen(username) >= 128 ||
        strlen(password) < 12 ||
        strlen(password) >= 128 ||
        strchr(password, '|') != NULL) {
        ESP_LOGE(TAG, "Invalid credential lengths or characters");
        goto cleanup;
    }

    rc = nvs_open("occ_opcua", NVS_READWRITE, &nvs);

    if (rc != ESP_OK) {
        ESP_LOGE(TAG, "OPC UA NVS open failed");
        goto cleanup;
    }

    rc = nvs_set_str(nvs, "username", username);

    if (rc == ESP_OK) {
        rc = nvs_set_str(nvs, "password", password);
    }

    if (rc == ESP_OK) {
        rc = nvs_commit(nvs);
    }

    nvs_close(nvs);

    if (rc == ESP_OK) {
        ESP_LOGI(TAG, "OPCUA_PROVISION_SUCCESS");
    } else {
        ESP_LOGE(TAG, "OPCUA_PROVISION_FAILED code=0x%x",
                 (unsigned)rc);
    }

cleanup:
    secure_wipe(line, sizeof(line));

    if (owns_driver) {
        uart_driver_delete(OCC_OPCUA_UART);
    }

    return rc;
}
