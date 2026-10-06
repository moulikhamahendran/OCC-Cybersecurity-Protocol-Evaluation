#pragma once

#include <stdbool.h>
#include <stddef.h>

#include "esp_err.h"

#define OCC_ENDPOINT_HOST_MAX_LEN 128

/*
 * Operational OCC network destination.
 *
 * Runtime configuration only.
 * Frozen FAIR-V1 benchmark code is unaffected.
 */
bool occ_endpoint_host_is_valid(
    const char *host
);

esp_err_t occ_endpoint_host_load(
    char *host,
    size_t host_size
);

esp_err_t occ_endpoint_host_save(
    const char *host
);
