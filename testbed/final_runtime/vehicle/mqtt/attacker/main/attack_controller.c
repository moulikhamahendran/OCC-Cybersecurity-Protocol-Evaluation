#include "attack_controller.h"

#include <string.h>

#include "freertos/FreeRTOS.h"

static portMUX_TYPE s_attack_lock =
    portMUX_INITIALIZER_UNLOCKED;

static occ_attack_mode_t s_attack_mode =
    OCC_ATTACK_MODE_IDLE;


void occ_attack_controller_init(void)
{
    taskENTER_CRITICAL(&s_attack_lock);

    s_attack_mode =
        OCC_ATTACK_MODE_IDLE;

    taskEXIT_CRITICAL(&s_attack_lock);
}


const char *occ_attack_mode_to_string(
    occ_attack_mode_t mode
)
{
    switch (mode) {
        case OCC_ATTACK_MODE_IDLE:
            return "IDLE";

        case OCC_ATTACK_MODE_SPOOF:
            return "SPOOF";

        case OCC_ATTACK_MODE_MALFORMED:
            return "MALFORMED";

        case OCC_ATTACK_MODE_REPLAY:
            return "REPLAY";

        case OCC_ATTACK_MODE_FLOOD:
            return "FLOOD";

        default:
            return "UNKNOWN";
    }
}


bool occ_attack_mode_from_string(
    const char *value,
    occ_attack_mode_t *mode
)
{
    if (
        value == NULL ||
        mode == NULL
    ) {
        return false;
    }

    if (
        strcmp(value, "spoof") == 0 ||
        strcmp(value, "SPOOF") == 0
    ) {
        *mode =
            OCC_ATTACK_MODE_SPOOF;

        return true;
    }

    if (
        strcmp(value, "malformed") == 0 ||
        strcmp(value, "MALFORMED") == 0
    ) {
        *mode =
            OCC_ATTACK_MODE_MALFORMED;

        return true;
    }

    if (
        strcmp(value, "replay") == 0 ||
        strcmp(value, "REPLAY") == 0
    ) {
        *mode =
            OCC_ATTACK_MODE_REPLAY;

        return true;
    }

    if (
        strcmp(value, "flood") == 0 ||
        strcmp(value, "FLOOD") == 0
    ) {
        *mode =
            OCC_ATTACK_MODE_FLOOD;

        return true;
    }

    if (
        strcmp(value, "idle") == 0 ||
        strcmp(value, "IDLE") == 0
    ) {
        *mode =
            OCC_ATTACK_MODE_IDLE;

        return true;
    }

    return false;
}


esp_err_t occ_attack_controller_arm(
    occ_attack_mode_t mode
)
{
    /*
     * First native-attack checkpoint:
     * only MALFORMED is implemented.
     */
    if (mode != OCC_ATTACK_MODE_MALFORMED) {
        return ESP_ERR_NOT_SUPPORTED;
    }

    taskENTER_CRITICAL(&s_attack_lock);

    s_attack_mode = mode;

    taskEXIT_CRITICAL(&s_attack_lock);

    return ESP_OK;
}


void occ_attack_controller_stop(void)
{
    taskENTER_CRITICAL(&s_attack_lock);

    s_attack_mode =
        OCC_ATTACK_MODE_IDLE;

    taskEXIT_CRITICAL(&s_attack_lock);
}


occ_attack_mode_t occ_attack_controller_mode(void)
{
    occ_attack_mode_t mode;

    taskENTER_CRITICAL(&s_attack_lock);

    mode = s_attack_mode;

    taskEXIT_CRITICAL(&s_attack_lock);

    return mode;
}


bool occ_attack_execution_enabled(void)
{
    /*
     * Native bounded MALFORMED execution is enabled.
     */
    return true;
}
