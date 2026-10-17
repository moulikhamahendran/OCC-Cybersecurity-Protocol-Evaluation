#pragma once
#include "esp_err.h"
/* Lab management only: independently polls OCC; no telemetry protocol change. */
esp_err_t occ_management_start(const char *vehicle_id, const char *occ_host);
