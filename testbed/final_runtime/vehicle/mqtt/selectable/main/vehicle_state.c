#include "vehicle_state.h"

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "esp_log.h"
#include "esp_timer.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"


static const char *TAG = "VEHICLE_CORE";

static portMUX_TYPE s_state_lock =
    portMUX_INITIALIZER_UNLOCKED;

static vehicle_state_t s_state;

static bool s_started = false;
static uint32_t s_period_ms = 100U;
static TaskHandle_t s_vehicle_task = NULL;


static void copy_state(
    vehicle_state_t *destination,
    const vehicle_state_t *source
)
{
    memcpy(
        destination,
        source,
        sizeof(*destination)
    );
}


static void initialize_vehicle_state(void)
{
    vehicle_state_t initial = {
        .seq = 0U,
        .t_source_us = esp_timer_get_time(),

        .speed = 0.80f,
        .pos_x = 0.0f,
        .pos_y = 0.0f,
        .heading = 0.0f,
        .battery_pct = 100.0f,

        .state = "RUNNING",
    };

    portENTER_CRITICAL(&s_state_lock);
    copy_state(&s_state, &initial);
    portEXIT_CRITICAL(&s_state_lock);
}


/*
 * Deterministic AGV-style physical workload.
 *
 * Route:
 *   (0,0) -> (20,0) -> (20,10)
 *   -> (0,10) -> (0,0) -> repeat
 *
 * This is intentionally deterministic rather than random so
 * C0/C1/C2 and later NORMAL/ATTACK conditions can use the
 * same logical vehicle workload.
 */
static void advance_vehicle_state(void)
{
    vehicle_state_t next;

    portENTER_CRITICAL(&s_state_lock);
    copy_state(&next, &s_state);
    portEXIT_CRITICAL(&s_state_lock);

    ++next.seq;

    next.t_source_us =
        esp_timer_get_time();

    /*
     * Deterministic speed variation:
     * 0.80 -> 1.20 -> 0.80 m/s.
     */
    const uint32_t speed_phase =
        (next.seq / 10U) % 40U;

    if (speed_phase <= 20U) {
        next.speed =
            0.80f +
            ((float)speed_phase * 0.02f);
    } else {
        next.speed =
            1.20f -
            ((float)(speed_phase - 20U) * 0.02f);
    }

    /*
     * Two-second deterministic stop every 30 seconds.
     * This makes the operational vehicle state realistic and
     * visibly exercises RUNNING/STOPPED states.
     */
    const uint32_t stop_phase =
        next.seq % 300U;

    if (stop_phase >= 280U) {
        next.speed = 0.0f;

        snprintf(
            next.state,
            sizeof(next.state),
            "%s",
            "STOPPED"
        );
    } else {
        snprintf(
            next.state,
            sizeof(next.state),
            "%s",
            "RUNNING"
        );

        const float dt_seconds =
            ((float)s_period_ms) / 1000.0f;

        const float distance =
            next.speed * dt_seconds;

        /*
         * Heading values:
         * 0   = east
         * 90  = north
         * 180 = west
         * 270 = south
         */
        if (
            next.heading < 45.0f ||
            next.heading >= 315.0f
        ) {
            next.heading = 0.0f;
            next.pos_x += distance;

            if (next.pos_x >= 20.0f) {
                next.pos_x = 20.0f;
                next.heading = 90.0f;
            }

        } else if (next.heading < 135.0f) {
            next.heading = 90.0f;
            next.pos_y += distance;

            if (next.pos_y >= 10.0f) {
                next.pos_y = 10.0f;
                next.heading = 180.0f;
            }

        } else if (next.heading < 225.0f) {
            next.heading = 180.0f;
            next.pos_x -= distance;

            if (next.pos_x <= 0.0f) {
                next.pos_x = 0.0f;
                next.heading = 270.0f;
            }

        } else {
            next.heading = 270.0f;
            next.pos_y -= distance;

            if (next.pos_y <= 0.0f) {
                next.pos_y = 0.0f;
                next.heading = 0.0f;
            }
        }
    }

    /*
     * Deterministic battery discharge.
     * At the default 10 Hz this is approximately
     * 0.6 percentage point per minute.
     */
    if (next.battery_pct > 20.0f) {
        next.battery_pct -= 0.001f;

        if (next.battery_pct < 20.0f) {
            next.battery_pct = 20.0f;
        }
    }

    portENTER_CRITICAL(&s_state_lock);
    copy_state(&s_state, &next);
    portEXIT_CRITICAL(&s_state_lock);

    /*
     * Local proof that the vehicle keeps running even when
     * MQTT/OCC/network communication is unavailable.
     */
    if (next.seq % 100U == 0U) {
        ESP_LOGI(
            TAG,
            "state seq=%lu speed=%.2f pos=(%.2f,%.2f) "
            "heading=%.1f battery=%.2f state=%s",
            (unsigned long)next.seq,
            (double)next.speed,
            (double)next.pos_x,
            (double)next.pos_y,
            (double)next.heading,
            (double)next.battery_pct,
            next.state
        );
    }
}


static void vehicle_state_task(void *argument)
{
    (void)argument;

    TickType_t last_wake =
        xTaskGetTickCount();

    TickType_t period_ticks =
        pdMS_TO_TICKS(s_period_ms);

    if (period_ticks == 0U) {
        period_ticks = 1U;
    }

    ESP_LOGI(
        TAG,
        "vehicle state task started period_ms=%lu",
        (unsigned long)s_period_ms
    );

    while (true) {
        advance_vehicle_state();

        vTaskDelayUntil(
            &last_wake,
            period_ticks
        );
    }
}


esp_err_t vehicle_state_start(uint32_t period_ms)
{
    if (period_ms == 0U) {
        return ESP_ERR_INVALID_ARG;
    }

    if (s_started) {
        return ESP_OK;
    }

    s_period_ms = period_ms;

    initialize_vehicle_state();

    const BaseType_t created =
        xTaskCreate(
            vehicle_state_task,
            "vehicle_state",
            4096,
            NULL,
            5,
            &s_vehicle_task
        );

    if (created != pdPASS) {
        s_vehicle_task = NULL;
        return ESP_ERR_NO_MEM;
    }

    s_started = true;

    return ESP_OK;
}


bool vehicle_state_get(vehicle_state_t *out_state)
{
    if (
        out_state == NULL ||
        !s_started
    ) {
        return false;
    }

    portENTER_CRITICAL(&s_state_lock);
    copy_state(out_state, &s_state);
    portEXIT_CRITICAL(&s_state_lock);

    return true;
}
