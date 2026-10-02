#pragma once

#include "esp_err.h"

#define OCC_MQTT_USERNAME_MAX_LEN 64
#define OCC_MQTT_PASSWORD_MAX_LEN 128

typedef enum {
    OCC_MQTT_PROFILE_C0 = 0,
    OCC_MQTT_PROFILE_C1,
    OCC_MQTT_PROFILE_C2,
} occ_mqtt_profile_t;

typedef struct {
    char username[OCC_MQTT_USERNAME_MAX_LEN];
    char password[OCC_MQTT_PASSWORD_MAX_LEN];
} occ_mqtt_credentials_t;


/*
 * Runtime MQTT security profile.
 *
 * Stored in NVS namespace "occ_runtime" under "mqtt_profile".
 */
const char *occ_mqtt_profile_to_string(
    occ_mqtt_profile_t profile
);

esp_err_t occ_mqtt_profile_from_string(
    const char *value,
    occ_mqtt_profile_t *profile
);

esp_err_t occ_mqtt_profile_load(
    occ_mqtt_profile_t *profile
);

esp_err_t occ_mqtt_profile_save(
    occ_mqtt_profile_t profile
);


/*
 * Load MQTT credentials from NVS.
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
 */
esp_err_t occ_mqtt_credentials_save(
    const char *username,
    const char *password
);
