#pragma once

#include <stdbool.h>

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * VM-003 attack-controller state.
 *
 * IMPORTANT:
 * This module DOES NOT execute attacks.
 *
 * It only records an explicitly armed mode.
 * Actual native attack generators are added in a later checkpoint.
 *
 * Boot/default state is always IDLE.
 */

typedef enum {
    OCC_ATTACK_MODE_IDLE = 0,
    OCC_ATTACK_MODE_SPOOF,
    OCC_ATTACK_MODE_MALFORMED,
    OCC_ATTACK_MODE_REPLAY,
    OCC_ATTACK_MODE_FLOOD,
} occ_attack_mode_t;

void occ_attack_controller_init(void);

const char *occ_attack_mode_to_string(
    occ_attack_mode_t mode
);

bool occ_attack_mode_from_string(
    const char *value,
    occ_attack_mode_t *mode
);

/*
 * Arm one attack type.
 *
 * Controller state only.
 * No malicious/attack traffic is generated here.
 */
esp_err_t occ_attack_controller_arm(
    occ_attack_mode_t mode
);

/*
 * Return controller to mandatory safe IDLE state.
 */
void occ_attack_controller_stop(void);

occ_attack_mode_t occ_attack_controller_mode(void);

/*
 * This checkpoint intentionally returns false.
 *
 * It provides an explicit invariant proving that attack
 * execution has not yet been enabled.
 */
bool occ_attack_execution_enabled(void);

#ifdef __cplusplus
}
#endif
