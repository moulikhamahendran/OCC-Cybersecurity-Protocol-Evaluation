idf_component_register(
    SRCS "fair_dds_benchmark.c" "fair_dds_codec.c" "fair_dds_network.c" "fair_dds_transport.c"
    INCLUDE_DIRS "include"
    REQUIRES fair_v1_core fair_dds_types microxrcedds esp_timer esp_event esp_wifi esp_netif nvs_flash freertos log
)
