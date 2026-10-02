idf_component_register(
    SRCS
        "main.c"
        "runtime_wifi.c"
        "runtime_mqtt_config.c"

    INCLUDE_DIRS
        "."

    REQUIRES
        mqtt
        json
        esp_wifi
        esp_event
        esp_netif
        nvs_flash
        wifi_provisioning
        esp_timer
        lwip

    EMBED_TXTFILES
        "fair_v1_c2_ca.crt"
)
