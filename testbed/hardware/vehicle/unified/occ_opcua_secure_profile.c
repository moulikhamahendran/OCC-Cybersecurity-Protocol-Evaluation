/* OCC Batch 2C: profile-aware client factory, based on existing formal profiles.
 * The same vehicle-1 cert is trusted for C1/C2; never flash it to VM-002.
 * C1/C2 differ by message mode, not by certificate. */
#include <stdint.h>
#include "occ_opcua_c2_server_cert.h"
#include "occ_opcua_c2_lab_ca.h"
#include <string.h>
#include <stdlib.h>
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "nvs.h"
#include "runtime_mqtt_config.h"
#include "fair_opcua_profile.h"
#include "occ_opcua_secure_profile.h"

static const char *TAG = "occ_opcua_secure";

extern const uint8_t occ_cert_begin[] asm("_binary_occ_opcua_client_cert_start");
extern const uint8_t occ_cert_end[] asm("_binary_occ_opcua_client_cert_end");
extern const uint8_t occ_key_begin[] asm("_binary_occ_opcua_client_key_start");
extern const uint8_t occ_key_end[] asm("_binary_occ_opcua_client_key_end");
extern const uint8_t occ_server_begin[] asm("_binary_occ_opcua_server_cert_start");
extern const uint8_t occ_server_end[] asm("_binary_occ_opcua_server_cert_end");

#define OCC_OPCUA_AUTH_MAX 128U

/* OCC_C1_INIT_DIAGNOSTICS: no secrets or certificate contents are logged. */
static void secure_init_checkpoint(const char *stage)
{
    bool intact = heap_caps_check_integrity_all(true);
    ESP_LOGI(TAG, "init_stage=%s heap_ok=%d free_internal=%lu largest_internal=%lu stack_min_bytes=%lu",
             stage, (int)intact,
             (unsigned long)heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
             (unsigned long)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
             (unsigned long)uxTaskGetStackHighWaterMark(NULL));
    if (!intact) {
        ESP_LOGE(TAG, "Heap corruption detected at stage=%s; stopping before further secure initialization", stage);
        abort();
    }
}


static void wipe_string(void *data, size_t n) {
    volatile uint8_t *p = (volatile uint8_t *)data;
    while (n--) { *p++ = 0; }
}

/* Dedicated credentials preferred. MQTT credentials are a documented
 * migration fallback only; server-side OPC UA authorization still applies. */
static bool load_opcua_credentials(char *user, size_t user_size,
                                   char *password, size_t password_size) {
    nvs_handle_t nvs;
    esp_err_t err = nvs_open("occ_opcua", NVS_READONLY, &nvs);
    if (err == ESP_OK) {
        size_t u_len = user_size;
        size_t p_len = password_size;
        esp_err_t u = nvs_get_str(nvs, "username", user, &u_len);
        esp_err_t p = nvs_get_str(nvs, "password", password, &p_len);
        nvs_close(nvs);
        if (u == ESP_OK && p == ESP_OK && user[0] && password[0]) {
            ESP_LOGI(TAG, "Using provisioned OPC UA credentials");
            return true;
        }
        wipe_string(user, user_size);
        wipe_string(password, password_size);
        /* Invalid/incomplete OPC UA credentials must not silently fall back. */
        if (u != ESP_ERR_NVS_NOT_FOUND || p != ESP_ERR_NVS_NOT_FOUND) {
            ESP_LOGE(TAG, "OPC UA credential record is incomplete/invalid");
            return false;
        }
    } else if (err != ESP_ERR_NVS_NOT_FOUND) {
        ESP_LOGE(TAG, "OPC UA credential NVS unavailable: %s", esp_err_to_name(err));
        return false;
    }

    occ_mqtt_credentials_t mqtt = {0};
    err = occ_mqtt_credentials_load(&mqtt);
    if (err != ESP_OK || !mqtt.username[0] || !mqtt.password[0]) {
        ESP_LOGE(TAG, "No secure OPC UA credentials; provision occ_opcua NVS");
        wipe_string(&mqtt, sizeof(mqtt));
        return false;
    }
    size_t u = strlen(mqtt.username), p = strlen(mqtt.password);
    if (u >= user_size || p >= password_size) {
        wipe_string(&mqtt, sizeof(mqtt));
        ESP_LOGE(TAG, "OPC UA credentials exceed supported length");
        return false;
    }
    memcpy(user, mqtt.username, u + 1U);
    memcpy(password, mqtt.password, p + 1U);
    wipe_string(&mqtt, sizeof(mqtt));
    ESP_LOGW(TAG, "Using existing MQTT credentials for OPC UA; verify server authorization");
    return true;
}


/* OCC experiment: minimal secure-channel policy, username auth unchanged.
 * This is a controlled test, not a verified production replacement. */
static UA_StatusCode occ_configure_basic256sha256_only(
    UA_ClientConfig *cfg, UA_ByteString cert, UA_ByteString key,
    UA_ByteString trustedServer, UA_ByteString issuerCA) {
    UA_StatusCode rc = UA_ClientConfig_setDefault(cfg);
    cfg->timeout = 30000U;
    if(rc != UA_STATUSCODE_GOOD) return rc;

    UA_TrustListDataType trust;
    UA_TrustListDataType_init(&trust);
    trust.specifiedLists = UA_TRUSTLISTMASKS_TRUSTEDCERTIFICATES;
    trust.trustedCertificates = (UA_ByteString*)UA_Array_new(
        1, &UA_TYPES[UA_TYPES_BYTESTRING]);
    if(!trust.trustedCertificates) return UA_STATUSCODE_BADOUTOFMEMORY;
    trust.trustedCertificatesSize = 1;
    rc = UA_ByteString_copy(&trustedServer, &trust.trustedCertificates[0]);
    if(rc != UA_STATUSCODE_GOOD) {
        UA_TrustListDataType_clear(&trust);
        return rc;
    }

    /* Preserve direct C2 server-certificate pinning.
       Add the verified issuing CA for C2 chain construction.
       C1 receives an empty issuer argument and is unchanged. */
    if(issuerCA.length > 0) {
        trust.specifiedLists |= UA_TRUSTLISTMASKS_ISSUERCERTIFICATES;
        trust.issuerCertificates = (UA_ByteString *)UA_Array_new(
            1, &UA_TYPES[UA_TYPES_BYTESTRING]);

        if(!trust.issuerCertificates) {
            UA_TrustListDataType_clear(&trust);
            return UA_STATUSCODE_BADOUTOFMEMORY;
        }

        trust.issuerCertificatesSize = 1;

        rc = UA_ByteString_copy(
            &issuerCA, &trust.issuerCertificates[0]);

        if(rc != UA_STATUSCODE_GOOD) {
            UA_TrustListDataType_clear(&trust);
            return rc;
        }
    }

    UA_NodeId groupId =
        UA_NS0ID(SERVERCONFIGURATION_CERTIFICATEGROUPS_DEFAULTAPPLICATIONGROUP);
    if(cfg->certificateVerification.clear)
        cfg->certificateVerification.clear(&cfg->certificateVerification);
    rc = UA_CertificateGroup_Memorystore(&cfg->certificateVerification,
                                         &groupId, &trust, cfg->logging, NULL);
    UA_TrustListDataType_clear(&trust);
    if(rc != UA_STATUSCODE_GOOD) return rc;

    /* Keep only the two policies needed for an authenticated secure session:
     * None for initial unsecured endpoint discovery, and Basic256Sha256 for
     * C1/C2 secure-channel negotiation. The actual session remains pinned to
     * cfg->securityMode=SIGN or SIGNANDENCRYPT and Basic256Sha256 URI.
     * Never automatically fall back to None on connect failures. */
    for(size_t i = 0; i < cfg->securityPoliciesSize; i++)
        if(cfg->securityPolicies[i].clear)
            cfg->securityPolicies[i].clear(&cfg->securityPolicies[i]);
    UA_free(cfg->securityPolicies);
    cfg->securityPolicies = NULL;
    cfg->securityPoliciesSize = 0;

    cfg->securityPolicies = (UA_SecurityPolicy*)UA_calloc(2U, sizeof(UA_SecurityPolicy));
    if(!cfg->securityPolicies) return UA_STATUSCODE_BADOUTOFMEMORY;

    rc = UA_SecurityPolicy_None(&cfg->securityPolicies[0],
                                UA_BYTESTRING_NULL, cfg->logging);
    if(rc != UA_STATUSCODE_GOOD) {
        if(cfg->securityPolicies[0].clear)
            cfg->securityPolicies[0].clear(&cfg->securityPolicies[0]);
        UA_free(cfg->securityPolicies);
        cfg->securityPolicies = NULL;
        return rc;
    }
    cfg->securityPoliciesSize = 1;

    rc = UA_SecurityPolicy_Basic256Sha256(&cfg->securityPolicies[1],
                                          cert, key, cfg->logging);
    if(rc != UA_STATUSCODE_GOOD) {
        if(cfg->securityPolicies[1].clear)
            cfg->securityPolicies[1].clear(&cfg->securityPolicies[1]);
        cfg->securityPolicies[0].clear(&cfg->securityPolicies[0]);
        UA_free(cfg->securityPolicies);
        cfg->securityPolicies = NULL;
        cfg->securityPoliciesSize = 0;
        return rc;
    }
    cfg->securityPoliciesSize = 2;
    return UA_STATUSCODE_GOOD;
}

UA_Client *occ_opcua_profile_create_client(occ_security_t security) {
    if (security == OCC_SECURITY_C0)
        return fair_opcua_profile_create_client();
    if (security != OCC_SECURITY_C1 && security != OCC_SECURITY_C2)
        return NULL;

    secure_init_checkpoint("before_credentials");
    char username[OCC_OPCUA_AUTH_MAX] = {0};
    char password[OCC_OPCUA_AUTH_MAX] = {0};
    if (!load_opcua_credentials(username, sizeof(username),
                                password, sizeof(password))) {
        wipe_string(username, sizeof(username));
        wipe_string(password, sizeof(password));
        return NULL;
    }

    secure_init_checkpoint("after_credentials");
    UA_Client *client = UA_Client_new();
    if (!client) goto fail;
    secure_init_checkpoint("after_client_new");
    UA_ClientConfig *cfg = UA_Client_getConfig(client);
    UA_ByteString cert = {
        .length = (size_t)(occ_cert_end - occ_cert_begin),
        .data = (UA_Byte *)(void *)occ_cert_begin
    };
    UA_ByteString key = {
        .length = (size_t)(occ_key_end - occ_key_begin),
        .data = (UA_Byte *)(void *)occ_key_begin
    };
    UA_ByteString server = {
        .length = (size_t)((security == OCC_SECURITY_C2 ? sizeof(occ_c2_server_cert_der) : (size_t)(occ_server_end - occ_server_begin))),
        .data = (UA_Byte *)(void *)(security == OCC_SECURITY_C2 ? occ_c2_server_cert_der : occ_server_begin)
    };

    UA_ByteString issuer = UA_BYTESTRING_NULL;

    if(security == OCC_SECURITY_C2) {
        issuer.length = sizeof(occ_c2_lab_ca_der);
        issuer.data = (UA_Byte *)(void *)occ_c2_lab_ca_der;
    }

    secure_init_checkpoint("before_encryption_config");
    UA_StatusCode rc = occ_configure_basic256sha256_only(
        cfg, cert, key, server, issuer);
    secure_init_checkpoint("after_encryption_config");
    if (rc != UA_STATUSCODE_GOOD) {
        ESP_LOGE(TAG, "Encryption policy initialization failed: 0x%08lx",
                 (unsigned long)rc);
        goto fail;
    }
    cfg->securityMode = security == OCC_SECURITY_C1
        ? UA_MESSAGESECURITYMODE_SIGN : UA_MESSAGESECURITYMODE_SIGNANDENCRYPT;
    UA_String_clear(&cfg->securityPolicyUri);
    cfg->securityPolicyUri = UA_STRING_ALLOC(
        "http://opcfoundation.org/UA/SecurityPolicy#Basic256Sha256");
    UA_String_clear(&cfg->clientDescription.applicationUri);
    /* Match the URI in the existing VM-001 DER certificate. */
    cfg->clientDescription.applicationUri =
        UA_STRING_ALLOC("urn:ovgu:occ:opcua:c1:esp32");
    if (!cfg->securityPolicyUri.data ||
        !cfg->clientDescription.applicationUri.data) goto fail;
    secure_init_checkpoint("before_authentication_config");
    rc = UA_ClientConfig_setAuthenticationUsername(cfg, username, password);
    secure_init_checkpoint("after_authentication_config");
    if (rc != UA_STATUSCODE_GOOD) {
        ESP_LOGE(TAG, "OPC UA authentication configuration failed: 0x%08lx",
                 (unsigned long)rc);
        goto fail;
    }
    cfg->localConnectionConfig.sendBufferSize = 8192U;
    cfg->localConnectionConfig.recvBufferSize = 8192U;
    wipe_string(username, sizeof(username));
    wipe_string(password, sizeof(password));
    secure_init_checkpoint("client_ready");
    return client;
fail:
    wipe_string(username, sizeof(username));
    wipe_string(password, sizeof(password));
    if (client) UA_Client_delete(client);
    return NULL;
}
