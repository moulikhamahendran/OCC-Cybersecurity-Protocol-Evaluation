#pragma once
#include "esp_err.h"
esp_err_t occ_dds_run(const char *vehicle_id, const char *gateway_ip, int security_level);
