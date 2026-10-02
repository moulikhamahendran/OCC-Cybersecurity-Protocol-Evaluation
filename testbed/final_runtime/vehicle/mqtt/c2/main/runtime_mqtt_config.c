#include "runtime_mqtt_config.h"

#include <stddef.h>
#include <string.h>

#include "nvs.h"

#define OCC_RUNTIME_NVS_NAMESPACE "occ_runtime"
#define OCC_MQTT_USERNAME_KEY     "mqtt_user"
#define OCC_MQTT_PASSWORD_KEY     "mqtt_pass"


esp_err_t occ_mqtt_credentials_load(
    occ_mqtt_credentials_t *credentials
)
{
    if (credentials == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    memset(
        credentials,
        0,
        sizeof(*credentials)
    );

    nvs_handle_t handle;

    esp_err_t err =
        nvs_open(
            OCC_RUNTIME_NVS_NAMESPACE,
            NVS_READONLY,
            &handle
        );

    if (err != ESP_OK) {
        return err;
    }

    size_t username_len =
        sizeof(credentials->username);

    err =
        nvs_get_str(
            handle,
            OCC_MQTT_USERNAME_KEY,
            credentials->username,
            &username_len
        );

    if (err != ESP_OK) {
        nvs_close(handle);
        memset(
            credentials,
            0,
            sizeof(*credentials)
        );
        return err;
    }

    size_t password_len =
        sizeof(credentials->password);

    err =
        nvs_get_str(
            handle,
            OCC_MQTT_PASSWORD_KEY,
            credentials->password,
            &password_len
        );

    nvs_close(handle);

    if (err != ESP_OK) {
        memset(
            credentials,
            0,
            sizeof(*credentials)
        );
        return err;
    }

    return ESP_OK;
}


esp_err_t occ_mqtt_credentials_save(
    const char *username,
    const char *password
)
{
    if (
        username == NULL ||
        password == NULL ||
        username[0] == '\0' ||
        password[0] == '\0' ||
        strlen(username) >= OCC_MQTT_USERNAME_MAX_LEN ||
        strlen(password) >= OCC_MQTT_PASSWORD_MAX_LEN
    ) {
        return ESP_ERR_INVALID_ARG;
    }

    nvs_handle_t handle;

    esp_err_t err =
        nvs_open(
            OCC_RUNTIME_NVS_NAMESPACE,
            NVS_READWRITE,
            &handle
        );

    if (err != ESP_OK) {
        return err;
    }

    err =
        nvs_set_str(
            handle,
            OCC_MQTT_USERNAME_KEY,
            username
        );

    if (err == ESP_OK) {
        err =
            nvs_set_str(
                handle,
                OCC_MQTT_PASSWORD_KEY,
                password
            );
    }

    if (err == ESP_OK) {
        err =
            nvs_commit(handle);
    }

    nvs_close(handle);

    return err;
}
