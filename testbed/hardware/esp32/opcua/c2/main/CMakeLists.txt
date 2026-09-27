idf_component_register(
    SRCS
        "main.c"
        "opcua_client.c"
    INCLUDE_DIRS "."
    REQUIRES
        esp_wifi
        esp_event
        esp_netif
        nvs_flash
        esp_timer
        open62541lib
    EMBED_FILES
        "certs/c1/esp32_client_cert.der"
        "certs/c1/esp32_client_key.der"
        "certs/c1/server_cert.der"
)
