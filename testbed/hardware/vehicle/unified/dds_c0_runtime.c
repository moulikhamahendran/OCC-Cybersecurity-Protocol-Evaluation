/* OCC_DDS_C0_STREAM_V1: controlled first-stage Micro XRCE-DDS uplink.
 * C0 only. No claim of C1/C2 or RF security. No benchmark echo statistics.
 */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "esp_err.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "uxr/client/client.h"
#include "fair_dds_transport.h"
#include "fair_dds_codec.h"
#include "telemetry_bridge.h"
#include "dds_c0_runtime.h"

#define OCC_DDS_ENCODE_BUFFER 768U
#define OCC_DDS_RETRY_MS 2000U
#define OCC_DDS_POLL_MS 50U
static const char *TAG="OCC_DDS_C0";

/* Transport enqueue_slot() is benchmark-specific and requires a finite
 * formal-run slot. Live telemetry carries a long-lived sequence, so send
 * directly using the transport's existing mutex-protected XRCE stream. */
/* OCC_DDS_C2_LIVE_ECHO_CALLBACK_V1
 * Continuous telemetry uses unrestricted uint32_t sequence numbers.
 * This callback is separate from the 600-slot FAIR-V1 benchmark.
 */
static void occ_dds_c2_live_echo(
    void *context,
    uint32_t seq,
    int64_t t_ack_rx_us
)
{
    (void)context;

    static unsigned long echo_count = 0UL;
    ++echo_count;

    if (echo_count <= 5UL || echo_count % 100UL == 0UL) {
        ESP_LOGI(
            TAG,
            "DDS C2 ECHO_RX seq=%lu total=%lu rx_us=%lld",
            (unsigned long)seq,
            echo_count,
            (long long)t_ack_rx_us
        );
    }
}

static bool send_live(fair_dds_transport_t *t, const char *data, size_t bytes)
{
    if (!t || !data || !bytes || !t->session_mutex) return false;
    if (xSemaphoreTake(t->session_mutex,pdMS_TO_TICKS(80))!=pdTRUE) return false;
    bool ok=false;
    if (t->session_created && t->entities_ready) {
        /* OCC_DDS_C2_RELIABLE_SOFT_RECOVERY_V1
         * C2 only: service reliable XRCE acknowledgments and retry
         * a full output window before counting an enqueue failure.
         * Keep the existing session and DDS endpoints whenever possible.
         */
        ok=uxr_buffer_topic(&t->session,t->reliable_out,t->telemetry_writer_id,
                            (uint8_t*)data,bytes);
        if (!ok && t->security_level == FAIR_DDS_SECURITY_C2) {
            (void)uxr_run_session_timeout(&t->session,80);
            ok=uxr_buffer_topic(&t->session,t->reliable_out,
                                t->telemetry_writer_id,
                                (uint8_t*)data,bytes);
            if (ok) {
                static unsigned c2_soft_recoveries=0U;
                c2_soft_recoveries++;
                if (c2_soft_recoveries==1U ||
                    c2_soft_recoveries%20U==0U)
                    ESP_LOGW(TAG,"C2 XRCE reliable stream recovered without reconnect");
            }
        }
        if (ok) uxr_flash_output_streams(&t->session);
    }
    xSemaphoreGive(t->session_mutex);
    return ok;
}

esp_err_t occ_dds_run(const char *vehicle_id,const char *gateway_ip,int security_level)
{
    if (!vehicle_id || !vehicle_id[0] || !gateway_ip || !gateway_ip[0] ||
        security_level < FAIR_DDS_SECURITY_C0 || security_level > FAIR_DDS_SECURITY_C2)
        return ESP_ERR_INVALID_ARG;
    static fair_dds_transport_t t;
    const char *port = security_level == FAIR_DDS_SECURITY_C0 ? "8888" :
                       security_level == FAIR_DDS_SECURITY_C1 ? "8891" : "8892";
    if (!fair_dds_transport_init(&t,gateway_ip,port,vehicle_id,security_level))
        return ESP_FAIL;
    /* OCC_DDS_C2_LIVE_ECHO_REGISTER_V1 */
    if (security_level == FAIR_DDS_SECURITY_C2) {
        if (fair_dds_transport_set_echo_callback(
                &t, occ_dds_c2_live_echo, NULL) != 0) {
            ESP_LOGE(TAG, "DDS C2 echo callback registration failed");
            return ESP_FAIL;
        }
        ESP_LOGI(TAG, "DDS C2 live echo callback registered");
    }

    ESP_LOGI(TAG,"XRCE target %s:%s (C%d)",gateway_ip,port,security_level);
    while (!fair_dds_transport_start(&t)) {
        ESP_LOGW(TAG,"Agent connection pending; retrying");
        vTaskDelay(pdMS_TO_TICKS(OCC_DDS_RETRY_MS));
    }
    ESP_LOGI(TAG,"XRCE session and DDS entities created");
    bool have_last=false;
    uint32_t last_seq=0;
    unsigned failed=0;
    while (true) {
        vehicle_state_t snap;
        fair_v1_payload_t payload;
        if (!occ_telemetry_snapshot(&snap,&payload,vehicle_id)) {
            vTaskDelay(pdMS_TO_TICKS(OCC_DDS_POLL_MS));
            continue;
        }
        if (have_last && snap.seq==last_seq) {
            vTaskDelay(pdMS_TO_TICKS(OCC_DDS_POLL_MS));
            continue;
        }
        char encoded[OCC_DDS_ENCODE_BUFFER];
        size_t length=0;
        if (!fair_dds_encode_payload(&payload,encoded,sizeof(encoded),&length)) {
            ESP_LOGE(TAG,"DDS encode failed seq=%lu",(unsigned long)snap.seq);
            vTaskDelay(pdMS_TO_TICKS(OCC_DDS_POLL_MS));
            continue;
        }
        if (!send_live(&t,encoded,length)) {
            failed++;
            if (failed%20U==1U)
                ESP_LOGW(TAG,"XRCE enqueue failed (%u); retrying",failed);
            /*
             * Entity creation does not guarantee reliable-stream progress.
             * A full output window can remain stuck even when ready() is
             * true. Recover after bounded consecutive enqueue failures.
             */
            if (failed >= 40U) {
                ESP_LOGW(TAG,
                    "XRCE stalled after %u enqueue failures; reconnecting",
                    failed);

                bool recovered = fair_dds_transport_reconnect(&t);

                if (recovered) {
                    ESP_LOGI(TAG,
                        "XRCE session re-established after stall");
                    have_last = false;
                } else {
                    ESP_LOGE(TAG,
                        "XRCE reconnect failed; will retry");
                }

                failed = 0U;
                vTaskDelay(pdMS_TO_TICKS(OCC_DDS_RETRY_MS));
            } else {
                vTaskDelay(pdMS_TO_TICKS(OCC_DDS_POLL_MS));
            }
            continue;
        }
        failed=0;
        last_seq=snap.seq;
        have_last=true;
        if ((snap.seq%100U)==0U)
            ESP_LOGI(TAG,"DDS C0 queued seq=%lu payload=%u",(unsigned long)snap.seq,(unsigned)length);
        vTaskDelay(pdMS_TO_TICKS(OCC_DDS_POLL_MS));
    }
    return ESP_OK;
}
