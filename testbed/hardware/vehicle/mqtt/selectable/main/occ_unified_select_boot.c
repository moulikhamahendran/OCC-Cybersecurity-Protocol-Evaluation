#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "esp_err.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "driver/uart.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "protocol_selection.h"

#define OCC_SELECT_UART UART_NUM_0
#define OCC_SELECT_WINDOW_MS 8000
#define OCC_SELECT_LINE_MAX 96

static const char *TAG = "OCC_UNIFIED_SELECT";

/*
 * Controlled laboratory USB selector.
 *
 * OPC UA C0, C1 and C2 selectable through local USB.
 * No credential namespaces or MQTT profile values are modified.
 */
esp_err_t occ_unified_select_boot(void)
{
    occ_protocol_selection_t current = {0};

    esp_err_t rc = occ_protocol_selection_load(&current);

    if (rc != ESP_OK) {
        ESP_LOGE(
            TAG,
            "Existing unified selection unavailable: %s",
            esp_err_to_name(rc)
        );
        return rc;
    }

    rc = uart_driver_install(
        OCC_SELECT_UART,
        2048,
        0,
        0,
        NULL,
        0
    );

    if (rc != ESP_OK) {
        ESP_LOGE(
            TAG,
            "USB selection unavailable: %s",
            esp_err_to_name(rc)
        );
        return rc;
    }

    uart_flush_input(OCC_SELECT_UART);

    ESP_LOGW(
        TAG,
        "OCC_UNIFIED_SELECT_READY window_ms=%d "
        "options=MQTT_C0,MQTT_C1,MQTT_C2,OPCUA_C0,OPCUA_C1,OPCUA_C2,DDS_C0,DDS_C1,DDS_C2",
        OCC_SELECT_WINDOW_MS
    );

    char line[OCC_SELECT_LINE_MAX] = {0};
    size_t length = 0;

    bool accepted = false;
    occ_protocol_t requested_protocol = OCC_PROTOCOL_OPCUA;
        occ_security_t requested_security = OCC_SECURITY_C0;

    const int64_t deadline =
        esp_timer_get_time() +
        (int64_t)OCC_SELECT_WINDOW_MS * 1000;

    while (esp_timer_get_time() < deadline) {
        uint8_t byte = 0;

        int count = uart_read_bytes(
            OCC_SELECT_UART,
            &byte,
            1,
            pdMS_TO_TICKS(50)
        );

        if (count <= 0) {
            continue;
        }

        if (byte == '\r') {
            continue;
        }

        if (byte == '\n') {
            line[length] = '\0';

            if (strcmp(line, "OCCSEL1|OPCUA|C0") == 0) {
                accepted = true;
                requested_security = OCC_SECURITY_C0;
            } else if (
                strcmp(line, "OCCSEL1|OPCUA|C1") == 0
            ) {
                accepted = true;
                requested_security = OCC_SECURITY_C1;
            } else if (
                strcmp(line, "OCCSEL1|OPCUA|C2") == 0
            ) {
                accepted = true;
                requested_security = OCC_SECURITY_C2;
        } else if (strcmp(line, "OCCSEL1|MQTT|C0") == 0) {
            accepted = true;
            requested_protocol = OCC_PROTOCOL_MQTT;
            requested_security = OCC_SECURITY_C0;
        } else if (strcmp(line, "OCCSEL1|MQTT|C1") == 0) {
            accepted = true;
            requested_protocol = OCC_PROTOCOL_MQTT;
            requested_security = OCC_SECURITY_C1;
        } else if (strcmp(line, "OCCSEL1|MQTT|C2") == 0) {
            accepted = true;
            requested_protocol = OCC_PROTOCOL_MQTT;
            requested_security = OCC_SECURITY_C2;
        } else if (strcmp(line, "OCCSEL1|DDS|C0") == 0) {
            accepted = true;
            requested_protocol = OCC_PROTOCOL_DDS;
            requested_security = OCC_SECURITY_C0;
        } else if (strcmp(line, "OCCSEL1|DDS|C1") == 0) {
            accepted = true;
            requested_protocol = OCC_PROTOCOL_DDS;
            requested_security = OCC_SECURITY_C1;
        } else if (strcmp(line, "OCCSEL1|DDS|C2") == 0) {
            accepted = true;
            requested_protocol = OCC_PROTOCOL_DDS;
            requested_security = OCC_SECURITY_C2;
        } else {
                ESP_LOGW(
                    TAG,
                    "OCC_UNIFIED_SELECT_REJECTED"
                );
            }

            break;
        }

        if (byte < 32 || byte > 126 ||
            length >= sizeof(line) - 1) {
            ESP_LOGW(
                TAG,
                "OCC_UNIFIED_SELECT_REJECTED"
            );
            break;
        }

        line[length++] = (char)byte;
    }

    uart_driver_delete(OCC_SELECT_UART);

    if (!accepted) {
        ESP_LOGI(
            TAG,
            "OCC_UNIFIED_SELECT_UNCHANGED"
        );
        return ESP_OK;
    }

    occ_protocol_selection_t requested = {
        .protocol = requested_protocol,
        .security = requested_security
    };

    if (!occ_protocol_selection_valid(&requested)) {
        return ESP_ERR_INVALID_ARG;
    }

    if (current.protocol == requested.protocol &&
        current.security == requested.security) {
        ESP_LOGI(
            TAG,
            "OCC_UNIFIED_SELECT_ALREADY_ACTIVE C%d",
            (int)requested.security
        );
        return ESP_OK;
    }

    rc = occ_protocol_selection_save(&requested);

    if (rc != ESP_OK) {
        ESP_LOGE(
            TAG,
            "OCC_UNIFIED_SELECT_SAVE_FAILED: %s",
            esp_err_to_name(rc)
        );
        return rc;
    }

    ESP_LOGW(
        TAG,
        "OCC_UNIFIED_SELECT_SAVED protocol=%s "
        "security=C%d",
        requested.protocol == OCC_PROTOCOL_MQTT ? "MQTT" : (requested.protocol == OCC_PROTOCOL_DDS ? "DDS" : "OPCUA"), (int)requested.security
    );

    ESP_LOGW(
        TAG,
        "OCC_UNIFIED_SELECT_RESTART"
    );

    vTaskDelay(pdMS_TO_TICKS(300));
    esp_restart();

    return ESP_OK;
}
