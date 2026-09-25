#include "opcua_client.h"

#include "open62541.h"
#include "esp_log.h"
#include "esp_timer.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include <sys/time.h>
#include <math.h>

static const char *TAG = "OPCUA_C0";

#define OPCUA_ENDPOINT "opc.tcp://192.168.1.115:4840/occ/"

#define TEST_DURATION_SECONDS 60
#define SAMPLE_RATE_HZ 10
#define TOTAL_SAMPLES (TEST_DURATION_SECONDS * SAMPLE_RATE_HZ)
#define SAMPLE_PERIOD_MS (1000 / SAMPLE_RATE_HZ)

static UA_UInt64 epoch_ms(void)
{
    struct timeval tv;
    gettimeofday(&tv, NULL);

    return ((UA_UInt64)tv.tv_sec * 1000ULL) +
           ((UA_UInt64)tv.tv_usec / 1000ULL);
}

static UA_StatusCode write_u32(
    UA_Client *client,
    const char *node,
    UA_UInt32 value)
{
    UA_Variant v;
    UA_Variant_init(&v);

    UA_Variant_setScalar(
        &v,
        &value,
        &UA_TYPES[UA_TYPES_UINT32]
    );

    return UA_Client_writeValueAttribute(
        client,
        UA_NODEID_STRING(2, (char *)node),
        &v
    );
}

static UA_StatusCode write_double(
    UA_Client *client,
    const char *node,
    UA_Double value)
{
    UA_Variant v;
    UA_Variant_init(&v);

    UA_Variant_setScalar(
        &v,
        &value,
        &UA_TYPES[UA_TYPES_DOUBLE]
    );

    return UA_Client_writeValueAttribute(
        client,
        UA_NODEID_STRING(2, (char *)node),
        &v
    );
}

static UA_StatusCode write_u64(
    UA_Client *client,
    const char *node,
    UA_UInt64 value)
{
    UA_Variant v;
    UA_Variant_init(&v);

    UA_Variant_setScalar(
        &v,
        &value,
        &UA_TYPES[UA_TYPES_UINT64]
    );

    return UA_Client_writeValueAttribute(
        client,
        UA_NODEID_STRING(2, (char *)node),
        &v
    );
}

void opcua_c0_test(void)
{
    ESP_LOGI(TAG, "====================================");
    ESP_LOGI(TAG, "OPC UA C0 60-SECOND HARDWARE CAMPAIGN");
    ESP_LOGI(TAG, "Rate: %d Hz", SAMPLE_RATE_HZ);
    ESP_LOGI(TAG, "Expected samples: %d", TOTAL_SAMPLES);
    ESP_LOGI(TAG, "====================================");

    UA_Client *client = UA_Client_new();

    if (!client) {
        ESP_LOGE(TAG, "UA_Client_new failed");
        return;
    }

    UA_ClientConfig_setDefault(
        UA_Client_getConfig(client)
    );

    UA_StatusCode rc =
        UA_Client_connect(client, OPCUA_ENDPOINT);

    if (rc != UA_STATUSCODE_GOOD) {
        ESP_LOGE(
            TAG,
            "CONNECT FAIL: %s",
            UA_StatusCode_name(rc)
        );

        UA_Client_delete(client);
        return;
    }

    ESP_LOGI(TAG, "OPC UA C0 CONNECTED");

    unsigned successful = 0;
    unsigned failed = 0;

    double rtt_sum_ms = 0.0;
    double jitter_sum_ms = 0.0;
    double previous_rtt_ms = 0.0;

    int64_t campaign_start_us = esp_timer_get_time();

    TickType_t last_wake = xTaskGetTickCount();

    for (UA_UInt32 seq = 1;
         seq <= TOTAL_SAMPLES;
         seq++) {

        UA_Double speed =
            2.5 + ((seq % 5) * 0.1);

        UA_Double battery =
            87.0 - ((double)seq * 0.001);

        UA_UInt64 timestamp_ms =
            epoch_ms();

        int64_t start_us =
            esp_timer_get_time();

        /* Write telemetry first.
           Sequence is written LAST as commit marker. */

        UA_StatusCode s1 = write_double(
            client,
            "Vehicle1.Speed",
            speed
        );

        UA_StatusCode s2 = write_double(
            client,
            "Vehicle1.Battery",
            battery
        );

        UA_StatusCode s3 = write_u64(
            client,
            "Vehicle1.TimestampMs",
            timestamp_ms
        );

        UA_StatusCode s4 = write_u32(
            client,
            "Vehicle1.Sequence",
            seq
        );

        UA_Variant read_value;
        UA_Variant_init(&read_value);

        UA_StatusCode sr =
            UA_Client_readValueAttribute(
                client,
                UA_NODEID_STRING(
                    2,
                    "Vehicle1.Sequence"
                ),
                &read_value
            );

        int64_t end_us =
            esp_timer_get_time();

        double rtt_ms =
            (end_us - start_us) / 1000.0;

        bool sequence_ok = false;

        if (sr == UA_STATUSCODE_GOOD &&
            UA_Variant_hasScalarType(
                &read_value,
                &UA_TYPES[UA_TYPES_UINT32]
            )) {

            UA_UInt32 received =
                *(UA_UInt32 *)read_value.data;

            sequence_ok = (received == seq);
        }

        bool sample_ok =
            s1 == UA_STATUSCODE_GOOD &&
            s2 == UA_STATUSCODE_GOOD &&
            s3 == UA_STATUSCODE_GOOD &&
            s4 == UA_STATUSCODE_GOOD &&
            sr == UA_STATUSCODE_GOOD &&
            sequence_ok;

        if (sample_ok) {

            successful++;
            rtt_sum_ms += rtt_ms;

            if (successful > 1) {
                jitter_sum_ms +=
                    fabs(rtt_ms - previous_rtt_ms);
            }

            previous_rtt_ms = rtt_ms;

        } else {

            failed++;
        }

        ESP_LOGI(
            TAG,
            "CSV,%lu,%llu,%.3f,%s",
            (unsigned long)seq,
            (unsigned long long)timestamp_ms,
            rtt_ms,
            sample_ok ? "PASS" : "FAIL"
        );

        UA_Variant_clear(&read_value);

        vTaskDelayUntil(
            &last_wake,
            pdMS_TO_TICKS(SAMPLE_PERIOD_MS)
        );
    }

    int64_t campaign_end_us =
        esp_timer_get_time();

    double elapsed_s =
        (campaign_end_us - campaign_start_us)
        / 1000000.0;

    double mean_rtt_ms =
        successful > 0
        ? rtt_sum_ms / successful
        : 0.0;

    double mean_jitter_ms =
        successful > 1
        ? jitter_sum_ms / (successful - 1)
        : 0.0;

    double throughput =
        successful / elapsed_s;

    double loss_percent =
        ((double)failed / TOTAL_SAMPLES) * 100.0;

    ESP_LOGI(TAG, "");
    ESP_LOGI(TAG, "=========== C0 RESULT ===========");
    ESP_LOGI(TAG, "Attempted       : %d", TOTAL_SAMPLES);
    ESP_LOGI(TAG, "Successful      : %u", successful);
    ESP_LOGI(TAG, "Failed          : %u", failed);
    ESP_LOGI(TAG, "Duration_s      : %.3f", elapsed_s);
    ESP_LOGI(TAG, "Mean_RTT_ms     : %.3f", mean_rtt_ms);
    ESP_LOGI(TAG, "Mean_Jitter_ms  : %.3f", mean_jitter_ms);
    ESP_LOGI(TAG, "Throughput_Hz   : %.3f", throughput);
    ESP_LOGI(TAG, "Loss_percent    : %.3f", loss_percent);
    ESP_LOGI(TAG, "=================================");
    ESP_LOGI(TAG, "");

    UA_Client_disconnect(client);
    UA_Client_delete(client);

    ESP_LOGI(
        TAG,
        "OPC UA C0 60-SECOND HARDWARE RUN COMPLETE"
    );
}
