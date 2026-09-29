#pragma once

#include "esp_err.h"
#include "freertos/FreeRTOS.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t fair_dds_network_connect(
    const char *ssid,
    const char *password,
    TickType_t timeout_ticks
);

esp_err_t fair_dds_network_sync_time(
    const char *sntp_server,
    TickType_t timeout_ticks
);

#ifdef __cplusplus
}
#endif
