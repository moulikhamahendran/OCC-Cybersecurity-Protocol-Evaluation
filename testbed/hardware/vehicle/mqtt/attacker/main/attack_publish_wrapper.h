#ifndef OCC_ATTACK_PUBLISH_WRAPPER_H
#define OCC_ATTACK_PUBLISH_WRAPPER_H

#include <stdio.h>
#include <string.h>
#include <stdbool.h>

#include "mqtt_client.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "attack_controller.h"

/*
 * Keep a callable reference to the REAL ESP-IDF publish function.
 * This function is defined BEFORE the macro below.
 */
static inline int occ_real_mqtt_publish(
        esp_mqtt_client_handle_t client,
        const char *topic,
        const char *data,
        int len,
        int qos,
        int retain)
{
    return esp_mqtt_client_publish(
        client,
        topic,
        data,
        len,
        qos,
        retain
    );
}

static inline bool occ_vm003_telemetry_topic(const char *topic)
{
    if (topic == NULL) {
        return false;
    }

    return strstr(topic, "/VM-003/") != NULL &&
           strstr(topic, "/telemetry") != NULL;
}

static inline int occ_effective_len(const char *data, int len)
{
    if (data == NULL) {
        return 0;
    }

    if (len > 0) {
        return len;
    }

    return (int)strlen(data);
}

/*
 * Replace only the serialNumber value.
 *
 * Topic remains:
 *
 *     .../VM-003/telemetry
 *
 * Payload becomes:
 *
 *     "serialNumber":"VM-001"
 *
 * This deliberately creates topic/payload identity mismatch.
 */
static inline bool occ_make_spoof_payload(
        const char *src,
        int src_len,
        char *dst,
        size_t dst_size,
        int *dst_len)
{
    if (src == NULL || dst == NULL || dst_size < 32) {
        return false;
    }

    int n = occ_effective_len(src, src_len);

    if (n <= 0 || (size_t)n >= dst_size) {
        return false;
    }

    memcpy(dst, src, (size_t)n);
    dst[n] = '\0';

    char *serial_key = strstr(dst, "\"serialNumber\"");

    if (serial_key == NULL) {
        return false;
    }

    char *vm = strstr(serial_key, "VM-003");

    if (vm == NULL) {
        return false;
    }

    /*
     * VM-003 and VM-001 are same length, therefore JSON length
     * and surrounding payload remain unchanged.
     */
    memcpy(vm, "VM-001", 6);

    if (dst_len != NULL) {
        *dst_len = n;
    }

    return true;
}

/*
 * MQTT publish interception for the LAB VM-003 telemetry path only.
 *
 * It does NOT redirect the target and does NOT modify control/status
 * topics.
 *
 * Every attack is intentionally finite.
 */
static inline int occ_attack_publish_wrapper(
        esp_mqtt_client_handle_t client,
        const char *topic,
        const char *data,
        int len,
        int qos,
        int retain)
{
    static char replay_payload[1024];
    static int replay_payload_len = 0;

    static char previous_mode[24] = "IDLE";

    static unsigned replay_count = 0;
    static unsigned spoof_count = 0;
    static bool flood_executed = false;

    /*
     * Only intercept physical VM-003 telemetry.
     */
    if (!occ_vm003_telemetry_topic(topic) || data == NULL) {
        return occ_real_mqtt_publish(
            client, topic, data, len, qos, retain
        );
    }

    int current_len = occ_effective_len(data, len);

    const char *mode =
        occ_attack_mode_to_string(
            occ_attack_controller_mode()
        );

    if (mode == NULL) {
        mode = "IDLE";
    }

    /*
     * Reset one-shot counters whenever operator changes attack mode.
     */
    if (strncmp(previous_mode, mode, sizeof(previous_mode) - 1) != 0) {

        replay_count = 0;
        spoof_count = 0;
        flood_executed = false;

        snprintf(
            previous_mode,
            sizeof(previous_mode),
            "%s",
            mode
        );

        printf(
            "[ATTACK] mode transition -> %s\n",
            mode
        );
    }

    /*
     * IDLE = legitimate telemetry.
     *
     * Continuously remember the last legitimate telemetry packet.
     * REPLAY will later retransmit this exact byte sequence.
     */
    if (strcmp(mode, "IDLE") == 0) {

        if (current_len > 0 &&
            current_len < (int)sizeof(replay_payload)) {

            memcpy(
                replay_payload,
                data,
                (size_t)current_len
            );

            replay_payload[current_len] = '\0';
            replay_payload_len = current_len;
        }

        return occ_real_mqtt_publish(
            client, topic, data, len, qos, retain
        );
    }

    /*
     * Keep the already-working MALFORMED implementation untouched.
     */
    if (strcmp(mode, "MALFORMED") == 0) {

        return occ_real_mqtt_publish(
            client, topic, data, len, qos, retain
        );
    }

    /* =====================================================
     * REPLAY
     * =====================================================
     *
     * Republish the exact previously accepted telemetry packet.
     *
     * Same:
     *   serialNumber
     *   seq
     *   t_source_us
     *   telemetry values
     *
     * OCC must reject seq <= last accepted seq.
     *
     * Attack automatically stops after 8 replay messages.
     */
    if (strcmp(mode, "REPLAY") == 0) {

        /*
         * Normally replay_payload already exists because VM-003
         * was publishing legitimate data before attack arming.
         *
         * Fallback: capture current packet first.
         */
        if (replay_payload_len <= 0) {

            if (current_len > 0 &&
                current_len < (int)sizeof(replay_payload)) {

                memcpy(
                    replay_payload,
                    data,
                    (size_t)current_len
                );

                replay_payload[current_len] = '\0';
                replay_payload_len = current_len;
            }

            printf(
                "[ATTACK][REPLAY] baseline captured; "
                "replay begins next telemetry cycle\n"
            );

            return occ_real_mqtt_publish(
                client, topic, data, len, qos, retain
            );
        }

        replay_count++;

        printf(
            "[ATTACK][REPLAY] replay packet %u/8\n",
            replay_count
        );

        int rc = occ_real_mqtt_publish(
            client,
            topic,
            replay_payload,
            replay_payload_len,
            qos,
            retain
        );

        if (replay_count >= 8) {

            printf(
                "[ATTACK][REPLAY] finite attack completed\n"
            );

            occ_attack_controller_stop();
        }

        return rc;
    }

    /* =====================================================
     * SPOOF
     * =====================================================
     *
     * MQTT topic:
     *
     *   occ/runtime/C2/VM-003/telemetry
     *
     * Payload identity:
     *
     *   serialNumber = VM-001
     *
     * OCC's existing topic/payload identity validation must reject it.
     *
     * Attack automatically stops after 8 spoofed packets.
     */
    if (strcmp(mode, "SPOOF") == 0) {

        char spoof_payload[1024];
        int spoof_len = 0;

        bool made = occ_make_spoof_payload(
            data,
            current_len,
            spoof_payload,
            sizeof(spoof_payload),
            &spoof_len
        );

        if (!made) {

            printf(
                "[ATTACK][SPOOF] ERROR: serialNumber VM-003 "
                "not found in payload\n"
            );

            occ_attack_controller_stop();

            return occ_real_mqtt_publish(
                client, topic, data, len, qos, retain
            );
        }

        spoof_count++;

        printf(
            "[ATTACK][SPOOF] packet %u/8: "
            "topic identity=VM-003 payload identity=VM-001\n",
            spoof_count
        );

        int rc = occ_real_mqtt_publish(
            client,
            topic,
            spoof_payload,
            spoof_len,
            qos,
            retain
        );

        if (spoof_count >= 8) {

            printf(
                "[ATTACK][SPOOF] finite attack completed\n"
            );

            occ_attack_controller_stop();
        }

        return rc;
    }

    /* =====================================================
     * FLOOD / DoS
     * =====================================================
     *
     * Controlled benchmark burst:
     *
     *       120 MQTT messages
     *       5 ms spacing
     *       approximately 0.6 s attack burst
     *
     * Same already-configured C2 connection.
     * Same VM-003 telemetry topic.
     *
     * No arbitrary host/port targeting is introduced.
     *
     * OCC flood detector threshold below = 30 msg/s.
     */
    if (strcmp(mode, "FLOOD") == 0) {

        if (!flood_executed) {

            flood_executed = true;

            printf(
                "[ATTACK][FLOOD] starting bounded burst: "
                "120 messages, 5 ms spacing\n"
            );

            int last_rc = 0;

            for (int i = 0; i < 120; ++i) {

                last_rc = occ_real_mqtt_publish(
                    client,
                    topic,
                    data,
                    len,
                    qos,
                    retain
                );

                if ((i + 1) % 20 == 0) {
                    printf(
                        "[ATTACK][FLOOD] sent %d/120\n",
                        i + 1
                    );
                }

                /*
                 * Yield to RTOS and avoid watchdog starvation.
                 */
                vTaskDelay(pdMS_TO_TICKS(5));
            }

            printf(
                "[ATTACK][FLOOD] bounded burst completed\n"
            );

            occ_attack_controller_stop();

            return last_rc;
        }

        return occ_real_mqtt_publish(
            client, topic, data, len, qos, retain
        );
    }

    /*
     * Unknown/non-executing controller mode:
     * preserve normal telemetry.
     */
    return occ_real_mqtt_publish(
        client, topic, data, len, qos, retain
    );
}

/*
 * Every esp_mqtt_client_publish() appearing AFTER this header
 * now passes through our lab attack wrapper.
 *
 * The wrapper itself can still call the original API through
 * occ_real_mqtt_publish().
 */
#define esp_mqtt_client_publish occ_attack_publish_wrapper

#endif
