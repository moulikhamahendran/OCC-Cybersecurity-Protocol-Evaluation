#include <stdint.h>

#include "open62541.h"

#include "fair_opcua_profile.h"

#if FAIR_OPCUA_PROFILE_SECURE

extern const uint8_t
    esp32_client_cert_der_start[]
    asm(
        "_binary_esp32_client_cert_der_start"
    );

extern const uint8_t
    esp32_client_cert_der_end[]
    asm(
        "_binary_esp32_client_cert_der_end"
    );

extern const uint8_t
    esp32_client_key_der_start[]
    asm(
        "_binary_esp32_client_key_der_start"
    );

extern const uint8_t
    esp32_client_key_der_end[]
    asm(
        "_binary_esp32_client_key_der_end"
    );

extern const uint8_t
    server_cert_der_start[]
    asm(
        "_binary_server_cert_der_start"
    );

extern const uint8_t
    server_cert_der_end[]
    asm(
        "_binary_server_cert_der_end"
    );

#endif

UA_Client *fair_opcua_profile_create_client(
    void
)
{
    UA_Client *client =
        UA_Client_new();

    if (
        client == NULL
    ) {
        return NULL;
    }

#if FAIR_OPCUA_PROFILE_SECURE

    UA_ClientConfig *config =
        UA_Client_getConfig(client);

    UA_ByteString client_cert = {
        .length =
            (size_t)(
                esp32_client_cert_der_end -
                esp32_client_cert_der_start
            ),

        .data =
            (UA_Byte *)
                esp32_client_cert_der_start
    };

    UA_ByteString client_key = {
        .length =
            (size_t)(
                esp32_client_key_der_end -
                esp32_client_key_der_start
            ),

        .data =
            (UA_Byte *)
                esp32_client_key_der_start
    };

    UA_ByteString server_cert = {
        .length =
            (size_t)(
                server_cert_der_end -
                server_cert_der_start
            ),

        .data =
            (UA_Byte *)
                server_cert_der_start
    };

    UA_StatusCode rc =
        UA_ClientConfig_setDefaultEncryption(
            config,
            client_cert,
            client_key,
            &server_cert,
            1U,
            NULL,
            0U
        );

    if (
        rc != UA_STATUSCODE_GOOD
    ) {
        UA_Client_delete(client);
        return NULL;
    }

#if FAIR_OPCUA_PROFILE_SIGN_AND_ENCRYPT

    config->securityMode =
        UA_MESSAGESECURITYMODE_SIGNANDENCRYPT;

#else

    config->securityMode =
        UA_MESSAGESECURITYMODE_SIGN;

#endif

    UA_String_clear(
        &config->securityPolicyUri
    );

    config->securityPolicyUri =
        UA_STRING_ALLOC(
            "http://opcfoundation.org/UA/SecurityPolicy#Basic256Sha256"
        );

    UA_String_clear(
        &config
            ->clientDescription
            .applicationUri
    );

    /*
     * Reuses the existing ESP32 certificate
     * application URI already present in the
     * verified secure hardware assets.
     */
    config
        ->clientDescription
        .applicationUri =
            UA_STRING_ALLOC(
                "urn:ovgu:occ:opcua:c1:esp32"
            );

    rc =
        UA_ClientConfig_setAuthenticationUsername(
            config,
            CONFIG_FAIR_OPCUA_USERNAME,
            CONFIG_FAIR_OPCUA_PASSWORD
        );

    if (
        rc != UA_STATUSCODE_GOOD
    ) {
        UA_Client_delete(client);
        return NULL;
    }

#else

    UA_ClientConfig *config =
        UA_Client_getConfig(client);

    UA_StatusCode rc =
        UA_ClientConfig_setDefault(
            config
        );

    if (
        rc != UA_STATUSCODE_GOOD
    ) {
        UA_Client_delete(client);
        return NULL;
    }

#endif

    /*
     * FAIR-V1 embedded OPC UA connection buffer.
     * Matches the open62541 LWIP static network buffer
     * and avoids a 64 KiB dynamic allocation on ESP32.
     */
    config->localConnectionConfig.sendBufferSize = 8192U;
    config->localConnectionConfig.recvBufferSize = 8192U;

    return client;
}
