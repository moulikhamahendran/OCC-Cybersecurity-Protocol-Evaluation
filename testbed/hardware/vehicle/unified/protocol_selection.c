#include "protocol_selection.h"

#include <stdint.h>
#include <stddef.h>
#include "nvs.h"

#define OCC_NVS_NAMESPACE "occ_unified"
#define OCC_NVS_SELECTION_KEY "selection"

#define OCC_SELECTION_VERSION_PREFIX 0x4F430100UL
#define OCC_SELECTION_VERSION_MASK   0xFFFFFF00UL

bool occ_protocol_selection_valid(
    const occ_protocol_selection_t *s
)
{
    return s != NULL &&
           s->protocol >= OCC_PROTOCOL_MQTT &&
           s->protocol <= OCC_PROTOCOL_DDS &&
           s->security >= OCC_SECURITY_C0 &&
           s->security <= OCC_SECURITY_C2;
}

esp_err_t occ_protocol_selection_load(
    occ_protocol_selection_t *selection
)
{
    if (selection == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    nvs_handle_t handle;
    esp_err_t err = nvs_open(
        OCC_NVS_NAMESPACE,
        NVS_READONLY,
        &handle
    );

    if (err != ESP_OK) {
        return err;
    }

    uint32_t encoded = 0;

    err = nvs_get_u32(
        handle,
        OCC_NVS_SELECTION_KEY,
        &encoded
    );

    nvs_close(handle);

    if (err != ESP_OK) {
        return err;
    }

    if ((encoded & OCC_SELECTION_VERSION_MASK) !=
        OCC_SELECTION_VERSION_PREFIX) {
        return ESP_ERR_INVALID_VERSION;
    }

    occ_protocol_selection_t candidate = {
        .protocol = (occ_protocol_t)((encoded >> 4) & 0x0F),
        .security = (occ_security_t)(encoded & 0x0F)
    };

    if (!occ_protocol_selection_valid(&candidate)) {
        return ESP_ERR_INVALID_STATE;
    }

    *selection = candidate;
    return ESP_OK;
}

esp_err_t occ_protocol_selection_save(
    const occ_protocol_selection_t *selection
)
{
    if (!occ_protocol_selection_valid(selection)) {
        return ESP_ERR_INVALID_ARG;
    }

    uint32_t encoded =
        OCC_SELECTION_VERSION_PREFIX |
        ((uint32_t)selection->protocol << 4) |
        (uint32_t)selection->security;

    nvs_handle_t handle;

    esp_err_t err = nvs_open(
        OCC_NVS_NAMESPACE,
        NVS_READWRITE,
        &handle
    );

    if (err != ESP_OK) {
        return err;
    }

    err = nvs_set_u32(
        handle,
        OCC_NVS_SELECTION_KEY,
        encoded
    );

    if (err == ESP_OK) {
        err = nvs_commit(handle);
    }

    nvs_close(handle);
    return err;
}
