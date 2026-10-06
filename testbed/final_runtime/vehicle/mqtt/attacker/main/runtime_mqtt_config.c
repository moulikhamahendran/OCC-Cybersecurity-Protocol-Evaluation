#include "runtime_mqtt_config.h"

#include <stddef.h>
#include <string.h>

#include "nvs.h"

#define OCC_RUNTIME_NVS_NAMESPACE "occ_runtime"
#define OCC_MQTT_USERNAME_KEY     "mqtt_user"
#define OCC_MQTT_PASSWORD_KEY     "mqtt_pass"
#define OCC_MQTT_PROFILE_KEY      "mqtt_profile"
#define OCC_VEHICLE_ID_KEY        "vehicle_id"


esp_err_t occ_vehicle_id_load(
    char *vehicle_id,
    size_t vehicle_id_size
)
{
    if (
        vehicle_id == NULL ||
        vehicle_id_size == 0U
    ) {
        return ESP_ERR_INVALID_ARG;
    }

    vehicle_id[0] = '\0';

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

    size_t stored_len = vehicle_id_size;

    err =
        nvs_get_str(
            handle,
            OCC_VEHICLE_ID_KEY,
            vehicle_id,
            &stored_len
        );

    nvs_close(handle);

    if (err != ESP_OK) {
        vehicle_id[0] = '\0';
        return err;
    }

    if (vehicle_id[0] == '\0') {
        return ESP_ERR_INVALID_STATE;
    }

    return ESP_OK;
}


esp_err_t occ_vehicle_id_save(
    const char *vehicle_id
)
{
    if (
        vehicle_id == NULL ||
        vehicle_id[0] == '\0' ||
        strlen(vehicle_id) >= OCC_VEHICLE_ID_MAX_LEN
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
            OCC_VEHICLE_ID_KEY,
            vehicle_id
        );

    if (err == ESP_OK) {
        err = nvs_commit(handle);
    }

    nvs_close(handle);

    return err;
}


const char *occ_mqtt_profile_to_string(
    occ_mqtt_profile_t profile
)
{
    switch (profile) {
        case OCC_MQTT_PROFILE_C0:
            return "C0";

        case OCC_MQTT_PROFILE_C1:
            return "C1";

        case OCC_MQTT_PROFILE_C2:
            return "C2";

        default:
            return "UNKNOWN";
    }
}


esp_err_t occ_mqtt_profile_from_string(
    const char *value,
    occ_mqtt_profile_t *profile
)
{
    if (
        value == NULL ||
        profile == NULL
    ) {
        return ESP_ERR_INVALID_ARG;
    }

    if (strcmp(value, "C0") == 0) {
        *profile = OCC_MQTT_PROFILE_C0;
        return ESP_OK;
    }

    if (strcmp(value, "C1") == 0) {
        *profile = OCC_MQTT_PROFILE_C1;
        return ESP_OK;
    }

    if (strcmp(value, "C2") == 0) {
        *profile = OCC_MQTT_PROFILE_C2;
        return ESP_OK;
    }

    return ESP_ERR_INVALID_ARG;
}


esp_err_t occ_mqtt_profile_load(
    occ_mqtt_profile_t *profile
)
{
    if (profile == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

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

    char value[8] = {0};
    size_t value_len = sizeof(value);

    err =
        nvs_get_str(
            handle,
            OCC_MQTT_PROFILE_KEY,
            value,
            &value_len
        );

    nvs_close(handle);

    if (err != ESP_OK) {
        return err;
    }

    return occ_mqtt_profile_from_string(
        value,
        profile
    );
}


esp_err_t occ_mqtt_profile_save(
    occ_mqtt_profile_t profile
)
{
    const char *value =
        occ_mqtt_profile_to_string(profile);

    if (strcmp(value, "UNKNOWN") == 0) {
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
            OCC_MQTT_PROFILE_KEY,
            value
        );

    if (err == ESP_OK) {
        err = nvs_commit(handle);
    }

    nvs_close(handle);

    return err;
}


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


esp_err_t occ_mqtt_credentials_clear(void)
{
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

    esp_err_t username_err =
        nvs_erase_key(
            handle,
            OCC_MQTT_USERNAME_KEY
        );

    if (
        username_err != ESP_OK &&
        username_err != ESP_ERR_NVS_NOT_FOUND
    ) {
        nvs_close(handle);
        return username_err;
    }

    esp_err_t password_err =
        nvs_erase_key(
            handle,
            OCC_MQTT_PASSWORD_KEY
        );

    if (
        password_err != ESP_OK &&
        password_err != ESP_ERR_NVS_NOT_FOUND
    ) {
        nvs_close(handle);
        return password_err;
    }

    err = nvs_commit(handle);

    nvs_close(handle);

    return err;
}
