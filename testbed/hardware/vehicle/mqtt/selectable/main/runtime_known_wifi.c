#include "runtime_known_wifi.h"

#include <stdio.h>
#include <string.h>

#include "esp_log.h"
#include "esp_wifi.h"
#include "nvs.h"

#define OCC_WIFI_NAMESPACE "occ_wifi"
#define OCC_WIFI_SSID_BYTES 33
#define OCC_WIFI_PASS_BYTES 65

/*
 * Do not switch networks after a single transient disconnect.
 */
#define OCC_WIFI_ROTATE_AFTER_DISCONNECTS 4U

static const char *TAG = "OCC_WIFI_MULTI";

static unsigned s_disconnect_count = 0U;


typedef struct {
    char ssid[OCC_WIFI_SSID_BYTES];
    char password[OCC_WIFI_PASS_BYTES];
    bool valid;
} occ_wifi_entry_t;


static void make_key(
    char *buffer,
    size_t buffer_size,
    const char *prefix,
    size_t index
)
{
    snprintf(
        buffer,
        buffer_size,
        "%s%u",
        prefix,
        (unsigned)index
    );
}


static bool load_entry(
    nvs_handle_t handle,
    size_t index,
    occ_wifi_entry_t *entry
)
{
    if (entry == NULL) {
        return false;
    }

    memset(
        entry,
        0,
        sizeof(*entry)
    );

    char ssid_key[8];
    char pass_key[8];

    make_key(
        ssid_key,
        sizeof(ssid_key),
        "s",
        index
    );

    make_key(
        pass_key,
        sizeof(pass_key),
        "p",
        index
    );

    size_t ssid_len =
        sizeof(entry->ssid);

    esp_err_t err =
        nvs_get_str(
            handle,
            ssid_key,
            entry->ssid,
            &ssid_len
        );

    if (
        err != ESP_OK ||
        entry->ssid[0] == '\0'
    ) {
        return false;
    }

    size_t pass_len =
        sizeof(entry->password);

    err =
        nvs_get_str(
            handle,
            pass_key,
            entry->password,
            &pass_len
        );

    /*
     * Missing password is acceptable for an open network.
     */
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        entry->password[0] = '\0';
    } else if (err != ESP_OK) {
        memset(
            entry,
            0,
            sizeof(*entry)
        );

        return false;
    }

    entry->valid = true;

    return true;
}


static esp_err_t save_network(
    const char *ssid,
    const char *password
)
{
    if (
        ssid == NULL ||
        password == NULL
    ) {
        return ESP_ERR_INVALID_ARG;
    }

    const size_t ssid_len =
        strnlen(
            ssid,
            OCC_WIFI_SSID_BYTES
        );

    const size_t pass_len =
        strnlen(
            password,
            OCC_WIFI_PASS_BYTES
        );

    if (
        ssid_len == 0U ||
        ssid_len >= OCC_WIFI_SSID_BYTES ||
        pass_len >= OCC_WIFI_PASS_BYTES
    ) {
        return ESP_ERR_INVALID_ARG;
    }

    nvs_handle_t handle;

    esp_err_t err =
        nvs_open(
            OCC_WIFI_NAMESPACE,
            NVS_READWRITE,
            &handle
        );

    if (err != ESP_OK) {
        return err;
    }

    size_t target = OCC_KNOWN_WIFI_MAX;
    size_t first_empty = OCC_KNOWN_WIFI_MAX;

    for (
        size_t i = 0U;
        i < OCC_KNOWN_WIFI_MAX;
        ++i
    ) {
        occ_wifi_entry_t entry;

        if (!load_entry(
                handle,
                i,
                &entry
            )) {
            if (
                first_empty ==
                OCC_KNOWN_WIFI_MAX
            ) {
                first_empty = i;
            }

            continue;
        }

        if (
            strcmp(
                entry.ssid,
                ssid
            ) == 0
        ) {
            /*
             * Avoid unnecessary NVS writes.
             */
            if (
                strcmp(
                    entry.password,
                    password
                ) == 0
            ) {
                nvs_close(handle);
                return ESP_OK;
            }

            target = i;
            break;
        }
    }

    if (
        target ==
        OCC_KNOWN_WIFI_MAX
    ) {
        if (
            first_empty !=
            OCC_KNOWN_WIFI_MAX
        ) {
            target = first_empty;
        } else {
            /*
             * Registry full.
             *
             * Replace the oldest/simple first slot.
             */
            target = 0U;
        }
    }

    char ssid_key[8];
    char pass_key[8];

    make_key(
        ssid_key,
        sizeof(ssid_key),
        "s",
        target
    );

    make_key(
        pass_key,
        sizeof(pass_key),
        "p",
        target
    );

    err =
        nvs_set_str(
            handle,
            ssid_key,
            ssid
        );

    if (err == ESP_OK) {
        err =
            nvs_set_str(
                handle,
                pass_key,
                password
            );
    }

    if (err == ESP_OK) {
        err =
            nvs_commit(handle);
    }

    nvs_close(handle);

    if (err == ESP_OK) {
        ESP_LOGI(
            TAG,
            "Known Wi-Fi stored SSID=%s",
            ssid
        );
    }

    return err;
}


esp_err_t occ_known_wifi_capture_current(void)
{
    wifi_config_t config;

    memset(
        &config,
        0,
        sizeof(config)
    );

    esp_err_t err =
        esp_wifi_get_config(
            WIFI_IF_STA,
            &config
        );

    if (err != ESP_OK) {
        return err;
    }

    const char *ssid =
        (const char *)config.sta.ssid;

    const char *password =
        (const char *)config.sta.password;

    if (
        ssid == NULL ||
        ssid[0] == '\0'
    ) {
        return ESP_ERR_INVALID_STATE;
    }

    return save_network(
        ssid,
        password != NULL
            ? password
            : ""
    );
}


size_t occ_known_wifi_count(void)
{
    nvs_handle_t handle;

    esp_err_t err =
        nvs_open(
            OCC_WIFI_NAMESPACE,
            NVS_READONLY,
            &handle
        );

    if (err != ESP_OK) {
        return 0U;
    }

    size_t count = 0U;

    for (
        size_t i = 0U;
        i < OCC_KNOWN_WIFI_MAX;
        ++i
    ) {
        occ_wifi_entry_t entry;

        if (load_entry(
                handle,
                i,
                &entry
            )) {
            ++count;
        }
    }

    nvs_close(handle);

    return count;
}


void occ_known_wifi_connected(void)
{
    s_disconnect_count = 0U;

    esp_err_t err =
        occ_known_wifi_capture_current();

    if (err != ESP_OK) {
        ESP_LOGW(
            TAG,
            "Unable to capture active Wi-Fi: %s",
            esp_err_to_name(err)
        );

        return;
    }

    ESP_LOGI(
        TAG,
        "Known Wi-Fi count=%u",
        (unsigned)occ_known_wifi_count()
    );
}


bool occ_known_wifi_rotate_after_disconnect(void)
{
    ++s_disconnect_count;

    if (
        s_disconnect_count <
        OCC_WIFI_ROTATE_AFTER_DISCONNECTS
    ) {
        return false;
    }

    s_disconnect_count = 0U;

    nvs_handle_t handle;

    esp_err_t err =
        nvs_open(
            OCC_WIFI_NAMESPACE,
            NVS_READONLY,
            &handle
        );

    if (err != ESP_OK) {
        return false;
    }

    occ_wifi_entry_t entries[
        OCC_KNOWN_WIFI_MAX
    ];

    memset(
        entries,
        0,
        sizeof(entries)
    );

    size_t valid_count = 0U;

    for (
        size_t i = 0U;
        i < OCC_KNOWN_WIFI_MAX;
        ++i
    ) {
        if (load_entry(
                handle,
                i,
                &entries[i]
            )) {
            ++valid_count;
        }
    }

    nvs_close(handle);

    if (valid_count <= 1U) {
        return false;
    }

    wifi_config_t current;

    memset(
        &current,
        0,
        sizeof(current)
    );

    err =
        esp_wifi_get_config(
            WIFI_IF_STA,
            &current
        );

    if (err != ESP_OK) {
        return false;
    }

    const char *current_ssid =
        (const char *)current.sta.ssid;

    size_t current_index =
        OCC_KNOWN_WIFI_MAX;

    for (
        size_t i = 0U;
        i < OCC_KNOWN_WIFI_MAX;
        ++i
    ) {
        if (
            entries[i].valid &&
            strcmp(
                entries[i].ssid,
                current_ssid
            ) == 0
        ) {
            current_index = i;
            break;
        }
    }

    size_t selected =
        OCC_KNOWN_WIFI_MAX;

    for (
        size_t offset = 1U;
        offset <= OCC_KNOWN_WIFI_MAX;
        ++offset
    ) {
        size_t index;

        if (
            current_index <
            OCC_KNOWN_WIFI_MAX
        ) {
            index =
                (
                    current_index +
                    offset
                ) %
                OCC_KNOWN_WIFI_MAX;
        } else {
            index =
                offset - 1U;
        }

        if (
            entries[index].valid &&
            strcmp(
                entries[index].ssid,
                current_ssid
            ) != 0
        ) {
            selected = index;
            break;
        }
    }

    if (
        selected ==
        OCC_KNOWN_WIFI_MAX
    ) {
        return false;
    }

    wifi_config_t next;

    memset(
        &next,
        0,
        sizeof(next)
    );

    const size_t selected_ssid_len =
        strnlen(
            entries[selected].ssid,
            sizeof(entries[selected].ssid)
        );

    const size_t selected_password_len =
        strnlen(
            entries[selected].password,
            sizeof(entries[selected].password)
        );

    if (
        selected_ssid_len == 0U ||
        selected_ssid_len >
            sizeof(next.sta.ssid) ||
        selected_password_len >
            sizeof(next.sta.password)
    ) {
        ESP_LOGW(
            TAG,
            "Saved Wi-Fi entry has invalid length"
        );

        return false;
    }

    memcpy(
        next.sta.ssid,
        entries[selected].ssid,
        selected_ssid_len
    );

    memcpy(
        next.sta.password,
        entries[selected].password,
        selected_password_len
    );

    /*
     * Let the access point decide the channel/BSSID.
     */
    next.sta.bssid_set = false;

    err =
        esp_wifi_set_config(
            WIFI_IF_STA,
            &next
        );

    if (err != ESP_OK) {
        ESP_LOGW(
            TAG,
            "Known Wi-Fi switch failed: %s",
            esp_err_to_name(err)
        );

        return false;
    }

    ESP_LOGW(
        TAG,
        "Switching to another known Wi-Fi SSID=%s",
        entries[selected].ssid
    );

    return true;
}


esp_err_t occ_known_wifi_request_reprovision(void)
{
    nvs_handle_t handle;

    esp_err_t err =
        nvs_open(
            OCC_WIFI_NAMESPACE,
            NVS_READWRITE,
            &handle
        );

    if (err != ESP_OK) {
        return err;
    }

    err =
        nvs_set_u8(
            handle,
            "force",
            1U
        );

    if (err == ESP_OK) {
        err =
            nvs_commit(handle);
    }

    nvs_close(handle);

    return err;
}


bool occ_known_wifi_consume_reprovision_request(void)
{
    nvs_handle_t handle;

    esp_err_t err =
        nvs_open(
            OCC_WIFI_NAMESPACE,
            NVS_READWRITE,
            &handle
        );

    if (err != ESP_OK) {
        return false;
    }

    uint8_t value = 0U;

    err =
        nvs_get_u8(
            handle,
            "force",
            &value
        );

    if (
        err != ESP_OK ||
        value != 1U
    ) {
        nvs_close(handle);
        return false;
    }

    nvs_erase_key(
        handle,
        "force"
    );

    nvs_commit(handle);
    nvs_close(handle);

    return true;
}
