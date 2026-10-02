idf_component_register(
    SRCS
        "main.c"
        "fair_mqtt_network.c"

    INCLUDE_DIRS
        "."

    REQUIRES
        mqtt
        json
        esp_wifi
        esp_event
        esp_netif
        nvs_flash
        esp_timer
        lwip
)
