#pragma once

#include <stdbool.h>
#include <stddef.h>

#include "esp_err.h"

/*
 * Operational network portability only.
 *
 * Stores a small set of known Wi-Fi networks in our own NVS
 * namespace so a newly provisioned network does not make the
 * previous one permanently unavailable.
 *
 * Passwords are never logged.
 */

#define OCC_KNOWN_WIFI_MAX 6

esp_err_t occ_known_wifi_capture_current(void);

void occ_known_wifi_connected(void);

/*
 * Called after a station disconnect.
 *
 * After several unsuccessful reconnects, rotate to another
 * saved network.
 *
 * Returns true if another saved configuration was selected.
 */
bool occ_known_wifi_rotate_after_disconnect(void);

/*
 * Request a one-time Wi-Fi reprovisioning boot.
 *
 * The request is persisted in NVS and consumed once.
 */
esp_err_t occ_known_wifi_request_reprovision(void);

bool occ_known_wifi_consume_reprovision_request(void);

size_t occ_known_wifi_count(void);
