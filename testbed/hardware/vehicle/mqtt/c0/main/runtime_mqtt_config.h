#pragma once

#include "esp_err.h"

#define OCC_MQTT_USERNAME_MAX_LEN 64
#define OCC_MQTT_PASSWORD_MAX_LEN 128

typedef struct {
    char username[OCC_MQTT_USERNAME_MAX_LEN];
    char password[OCC_MQTT_PASSWORD_MAX_LEN];
} occ_mqtt_credentials_t;

/*
 * Load MQTT credentials from the ESP32 NVS namespace "occ_runtime".
 *
 * Credentials are runtime data:
 * - not stored in Git
 * - not stored in Kconfig
 * - not logged
 */
esp_err_t occ_mqtt_credentials_load(
    occ_mqtt_credentials_t *credentials
);

/*
 * Save MQTT credentials into NVS.
 * This will later be called by the provisioning path.
 */
esp_err_t occ_mqtt_credentials_save(
    const char *username,
    const char *password
);
