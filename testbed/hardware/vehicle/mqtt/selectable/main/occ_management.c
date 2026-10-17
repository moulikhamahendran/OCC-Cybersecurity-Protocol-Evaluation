#include "occ_management.h"
#include "occ_mgmt_private.h"   /* Generated locally; never commit or upload. */
#include "protocol_selection.h"
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "esp_log.h"
#include "esp_system.h"
#include "esp_random.h"
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "lwip/sockets.h"
#include "lwip/netdb.h"
#include "nvs.h"
#include "mbedtls/md.h"

#define OCC_MGMT_PORT "18081"
#define OCC_MGMT_PERIOD_MS 5000
#define OCC_MGMT_STACK 6144
#define OCC_MGMT_LINE 256

static const char *TAG = "OCC_MGMT";
static char s_vehicle[33];
static char s_host[128];
static bool s_started = false;

static bool hmac_hex(const char *text, char hex[65]) {
    unsigned char out[32];
    const mbedtls_md_info_t *info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
    if (!info || mbedtls_md_hmac(info, occ_mgmt_psk, sizeof(occ_mgmt_psk),
                (const unsigned char *)text, strlen(text), out) != 0) return false;
    static const char digits[] = "0123456789abcdef";
    for (int i = 0; i < 32; ++i) {
        hex[2*i] = digits[out[i] >> 4];
        hex[2*i+1] = digits[out[i] & 0x0f];
    }
    hex[64] = '\0';
    memset(out, 0, sizeof(out));
    return true;
}

static bool safe_equal(const char *a, const char *b, size_t n) {
    unsigned diff = 0;
    for (size_t i = 0; i < n; ++i) diff |= (unsigned)(unsigned char)(a[i] ^ b[i]);
    return diff == 0;
}

static bool valid_request_id(const char *s) {
    if (!s || strlen(s) != 32) return false;
    for (size_t i = 0; i < 32; ++i) {
        if (!((s[i] >= '0' && s[i] <= '9') ||
              (s[i] >= 'a' && s[i] <= 'f'))) return false;
    }
    return true;
}

static void read_last(char out[33]) {
    strcpy(out, "-");
    nvs_handle_t h;
    if (nvs_open("occ_mgmt", NVS_READONLY, &h) != ESP_OK) return;
    char tmp[33] = {0}; size_t size = sizeof(tmp);
    if (nvs_get_str(h, "last", tmp, &size) == ESP_OK && valid_request_id(tmp))
        memcpy(out, tmp, 33);
    nvs_close(h);
}

static esp_err_t save_last(const char *id) {
    if (!valid_request_id(id)) return ESP_ERR_INVALID_ARG;
    nvs_handle_t h;
    esp_err_t rc = nvs_open("occ_mgmt", NVS_READWRITE, &h);
    if (rc != ESP_OK) return rc;
    rc = nvs_set_str(h, "last", id);
    if (rc == ESP_OK) rc = nvs_commit(h);
    nvs_close(h);
    return rc;
}

static const char *protocol_name(occ_protocol_t p) {
    if (p == OCC_PROTOCOL_MQTT) return "MQTT";
    if (p == OCC_PROTOCOL_OPCUA) return "OPCUA";
    if (p == OCC_PROTOCOL_DDS) return "DDS";
    return "UNKNOWN";
}

static bool parse_response(char *line, const char *nonce,
                           occ_protocol_selection_t *wanted, char request_id[33]) {
    char *signature = strrchr(line, '|');
    if (!signature || strlen(signature + 1) != 64) return false;
    *signature++ = '\0';
    char expected[65];
    if (!hmac_hex(line, expected) || !safe_equal(signature, expected, 64)) return false;

    char *save = NULL;
    char *parts[6] = {0};
    for (int i = 0; i < 6; ++i) {
        parts[i] = strtok_r(i == 0 ? line : NULL, "|", &save);
        if (!parts[i]) return false;
    }
    if (strtok_r(NULL, "|", &save)) return false;
    if (strcmp(parts[1], s_vehicle) || strcmp(parts[2], nonce)) return false;
    if (!strcmp(parts[0], "NOP1")) return false;
    if (strcmp(parts[0], "CMD1") || !valid_request_id(parts[3])) return false;
    if (!strcmp(parts[4], "MQTT")) wanted->protocol = OCC_PROTOCOL_MQTT;
    else if (!strcmp(parts[4], "OPCUA")) wanted->protocol = OCC_PROTOCOL_OPCUA;
    else if (!strcmp(parts[4], "DDS")) wanted->protocol = OCC_PROTOCOL_DDS;
    else return false;
    if (!strcmp(parts[5], "C0")) wanted->security = OCC_SECURITY_C0;
    else if (!strcmp(parts[5], "C1")) wanted->security = OCC_SECURITY_C1;
    else if (!strcmp(parts[5], "C2")) wanted->security = OCC_SECURITY_C2;
    else return false;
    if (!occ_protocol_selection_valid(wanted)) return false;
    if (wanted->protocol == OCC_PROTOCOL_DDS && wanted->security != OCC_SECURITY_C0) return false;
    memcpy(request_id, parts[3], 33);
    return true;
}

static void poll_once(void) {
    occ_protocol_selection_t current = {0};
    if (occ_protocol_selection_load(&current) != ESP_OK) return;
    if (current.protocol != OCC_PROTOCOL_MQTT && current.protocol != OCC_PROTOCOL_OPCUA && current.protocol != OCC_PROTOCOL_DDS) return;
    char last[33]; read_last(last);
    char nonce[17];
    snprintf(nonce, sizeof(nonce), "%08" PRIx32 "%08" PRIx32,
             esp_random(), esp_random());
    char body[170];
    int n = snprintf(body, sizeof(body), "POLL1|%s|%s|%s|%s|C%d",
                     s_vehicle, nonce, last, protocol_name(current.protocol), (int)current.security);
    if (n <= 0 || n >= (int)sizeof(body)) return;
    char digest[65]; if (!hmac_hex(body, digest)) return;
    char packet[OCC_MGMT_LINE];
    n = snprintf(packet, sizeof(packet), "%s|%s", body, digest);
    if (n <= 0 || n >= (int)sizeof(packet)) return;

    struct addrinfo hints = { .ai_family = AF_INET, .ai_socktype = SOCK_DGRAM };
    struct addrinfo *dest = NULL;
    if (getaddrinfo(s_host, OCC_MGMT_PORT, &hints, &dest) != 0 || !dest) return;
    int fd = socket(dest->ai_family, dest->ai_socktype, dest->ai_protocol);
    if (fd < 0) { freeaddrinfo(dest); return; }
    struct timeval timeout = { .tv_sec = 2, .tv_usec = 0 };
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    if (sendto(fd, packet, n, 0, dest->ai_addr, dest->ai_addrlen) != n) {
        close(fd); freeaddrinfo(dest); return;
    }
    char reply[OCC_MGMT_LINE];
    ssize_t len = recvfrom(fd, reply, sizeof(reply)-1, 0, NULL, NULL);
    close(fd); freeaddrinfo(dest);
    if (len <= 0 || len >= (ssize_t)sizeof(reply)) return;
    reply[len] = '\0';
    occ_protocol_selection_t desired = {0}; char id[33];
    if (!parse_response(reply, nonce, &desired, id)) return;
    if (!strcmp(id, last)) return; // Duplicate command: never restart twice.
    if (current.protocol == desired.protocol && current.security == desired.security) {
        if (save_last(id) != ESP_OK) ESP_LOGE(TAG, "Cannot save acknowledgement");
        return;
    }
    // Store request identity first. Never restart unless both writes succeed.
    if (save_last(id) != ESP_OK) {
        ESP_LOGE(TAG, "Management request-id NVS write failed");
        return;
    }
    if (occ_protocol_selection_save(&desired) != ESP_OK) {
        ESP_LOGE(TAG, "Management mode NVS write failed; no restart");
        return;
    }
    ESP_LOGW(TAG, "Authenticated switch accepted: %s C%d", protocol_name(desired.protocol), (int)desired.security);
    vTaskDelay(pdMS_TO_TICKS(250));
    esp_restart();
}

static void management_task(void *unused) {
    (void)unused;
    while (true) {
        // Avoid adding network crypto load during low-heap OPC UA secure sessions.
        if (heap_caps_get_free_size(MALLOC_CAP_8BIT) > 45000)
            poll_once();
        vTaskDelay(pdMS_TO_TICKS(OCC_MGMT_PERIOD_MS));
    }
}

esp_err_t occ_management_start(const char *vehicle_id, const char *occ_host) {
    if (s_started) return ESP_OK;
    if (!vehicle_id || !occ_host || strlen(vehicle_id) < 1 || strlen(vehicle_id) > 32 ||
        strlen(occ_host) < 1 || strlen(occ_host) >= sizeof(s_host)) return ESP_ERR_INVALID_ARG;
    for (const char *p = vehicle_id; *p; ++p) {
        if (!( (*p >= '0' && *p <= '9') || (*p >= 'A' && *p <= 'Z') ||
               (*p >= 'a' && *p <= 'z') || *p == '-' || *p == '_')) return ESP_ERR_INVALID_ARG;
    }
    strcpy(s_vehicle, vehicle_id); strcpy(s_host, occ_host);
    if (xTaskCreate(management_task, "occ_mgmt", OCC_MGMT_STACK, NULL, 4, NULL) != pdPASS)
        return ESP_ERR_NO_MEM;
    s_started = true;
    ESP_LOGI(TAG, "Independent authenticated management task started (UDP %s)", OCC_MGMT_PORT);
    return ESP_OK;
}
