idf_component_register(
    SRCS
        "main.c"
        "vehicle_state.c"
        "runtime_wifi.c"
        "runtime_mqtt_config.c"
        "runtime_endpoint_config.c"
        "runtime_known_wifi.c"

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
        esp_driver_gpio
        esp_timer
        lwip

    EMBED_TXTFILES
        "fair_v1_c2_ca.crt"
)
