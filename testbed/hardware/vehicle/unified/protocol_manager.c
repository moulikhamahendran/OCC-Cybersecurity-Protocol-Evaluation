#include "protocol_manager.h"
#include "nvs.h"

#include <string.h>

esp_err_t occ_protocol_manager_resolve(
    occ_protocol_manager_t *manager,
    occ_security_t existing_mqtt_security
)
{
    if (!manager ||
        existing_mqtt_security < OCC_SECURITY_C0 ||
        existing_mqtt_security > OCC_SECURITY_C2) {
        return ESP_ERR_INVALID_ARG;
    }

    memset(manager, 0, sizeof(*manager));
    manager->backend = OCC_RUNTIME_UNAVAILABLE;



    esp_err_t err = occ_protocol_selection_load(
        &manager->selection
    );

    if (err == ESP_ERR_NVS_NOT_FOUND) {
        manager->selection.protocol = OCC_PROTOCOL_MQTT;
        manager->selection.security = existing_mqtt_security;
        manager->backend = OCC_RUNTIME_MQTT;
        return ESP_OK;
    }

    if (err != ESP_OK) {
        return err;
    }

    manager->explicitly_configured = true;

    if (manager->selection.protocol == OCC_PROTOCOL_MQTT) {
        if (manager->selection.security != existing_mqtt_security) {
            return ESP_ERR_INVALID_STATE;
        }

        manager->backend = OCC_RUNTIME_MQTT;
        return ESP_OK;
    }

    if (manager->selection.protocol == OCC_PROTOCOL_OPCUA) {
        switch (manager->selection.security) {
            case OCC_SECURITY_C0: manager->backend = OCC_RUNTIME_OPCUA_C0; return ESP_OK;
            case OCC_SECURITY_C1: manager->backend = OCC_RUNTIME_OPCUA_C1; return ESP_OK;
            case OCC_SECURITY_C2: manager->backend = OCC_RUNTIME_OPCUA_C2; return ESP_OK;
            default: return ESP_ERR_NOT_SUPPORTED;
        }
    }

    /* OCC_DDS_C0_STREAM_V1: do not advertise C1/C2 until implemented. */
    if (manager->selection.protocol == OCC_PROTOCOL_DDS) {
        switch (manager->selection.security) {
            case OCC_SECURITY_C0: manager->backend = OCC_RUNTIME_DDS_C0; return ESP_OK;
            case OCC_SECURITY_C1: manager->backend = OCC_RUNTIME_DDS_C1; return ESP_OK;
            case OCC_SECURITY_C2: manager->backend = OCC_RUNTIME_DDS_C2; return ESP_OK;
            default: return ESP_ERR_NOT_SUPPORTED;
        }
    }
    return ESP_ERR_NOT_SUPPORTED;
}
