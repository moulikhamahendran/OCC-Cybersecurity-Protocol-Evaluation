#include "runtime_endpoint_config.h"

#include <ctype.h>
#include <string.h>

#include "nvs.h"

#define OCC_ENDPOINT_NAMESPACE "occ_endpoint"
#define OCC_ENDPOINT_HOST_KEY  "host"


bool occ_endpoint_host_is_valid(
    const char *host
)
{
    if (host == NULL) {
        return false;
    }

    const size_t len = strlen(host);

    if (
        len == 0U ||
        len >= OCC_ENDPOINT_HOST_MAX_LEN
    ) {
        return false;
    }

    for (size_t i = 0U; i < len; ++i) {
        const unsigned char c =
            (unsigned char)host[i];

        const bool allowed =
            isalnum(c) ||
            c == '.' ||
            c == '-' ||
            c == '_';

        if (!allowed) {
            return false;
        }
    }

    return true;
}


esp_err_t occ_endpoint_host_load(
    char *host,
    size_t host_size
)
{
    if (
        host == NULL ||
        host_size == 0U
    ) {
        return ESP_ERR_INVALID_ARG;
    }

    nvs_handle_t handle;

    esp_err_t err =
        nvs_open(
            OCC_ENDPOINT_NAMESPACE,
            NVS_READONLY,
            &handle
        );

    if (err != ESP_OK) {
        return err;
    }

    size_t required = host_size;

    err =
        nvs_get_str(
            handle,
            OCC_ENDPOINT_HOST_KEY,
            host,
            &required
        );

    nvs_close(handle);

    if (err != ESP_OK) {
        return err;
    }

    if (!occ_endpoint_host_is_valid(host)) {
        memset(
            host,
            0,
            host_size
        );

        return ESP_ERR_INVALID_STATE;
    }

    return ESP_OK;
}


esp_err_t occ_endpoint_host_save(
    const char *host
)
{
    if (!occ_endpoint_host_is_valid(host)) {
        return ESP_ERR_INVALID_ARG;
    }

    nvs_handle_t handle;

    esp_err_t err =
        nvs_open(
            OCC_ENDPOINT_NAMESPACE,
            NVS_READWRITE,
            &handle
        );

    if (err != ESP_OK) {
        return err;
    }

    err =
        nvs_set_str(
            handle,
            OCC_ENDPOINT_HOST_KEY,
            host
        );

    if (err == ESP_OK) {
        err = nvs_commit(handle);
    }

    nvs_close(handle);

    return err;
}
