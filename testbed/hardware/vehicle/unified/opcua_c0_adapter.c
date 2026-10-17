/* OCC_C0_DIAGNOSTICS_V1 */
#include "opcua_c0_adapter.h"
#include "telemetry_bridge.h"
#include "esp_timer.h"
#include "esp_log.h"

#include <stdio.h>
#include <string.h>
#include "occ_opcua_secure_profile.h"

bool occ_opcua_profile_init(
    occ_opcua_c0_adapter_t *a,
    const char *endpoint,
    const char *vehicle_id,
    occ_security_t security
)
{
    if (!a || !endpoint || !vehicle_id ||
        !endpoint[0] || !vehicle_id[0] ||
        security < OCC_SECURITY_C0 || security > OCC_SECURITY_C2) {
        return false;
    }

    size_t endpoint_len = strlen(endpoint);
    size_t vehicle_len = strlen(vehicle_id);

    if (endpoint_len >= sizeof(a->endpoint) ||
        vehicle_len >= sizeof(a->vehicle_id)) {
        return false;
    }

    memset(a, 0, sizeof(*a));
    a->security = security;

    memcpy(a->endpoint, endpoint, endpoint_len + 1);
    memcpy(a->vehicle_id, vehicle_id, vehicle_len + 1);

    return true;
}

bool occ_opcua_c0_init(occ_opcua_c0_adapter_t *a,
                       const char *endpoint, const char *vehicle_id) {
    return occ_opcua_profile_init(a, endpoint, vehicle_id, OCC_SECURITY_C0);
}

UA_StatusCode occ_opcua_c0_start(
    occ_opcua_c0_adapter_t *a
)
{
    if (!a || !a->endpoint[0] || !a->vehicle_id[0] ||
        a->client) {
        return UA_STATUSCODE_BADINVALIDSTATE;
    }

    a->client = occ_opcua_profile_create_client(a->security);

    if (!a->client) {
        return UA_STATUSCODE_BADOUTOFMEMORY;
    }

    if (!fair_opcua_transport_init(
            &a->transport,
            a->client,
            a->endpoint,
            a->vehicle_id)) {
        UA_Client_delete(a->client);
        a->client = NULL;
        return UA_STATUSCODE_BADINTERNALERROR;
    }

    a->transport.operational_telemetry = true;

    UA_StatusCode rc =
        fair_opcua_transport_connect(&a->transport);

    if (rc != UA_STATUSCODE_GOOD) {
        fair_opcua_transport_stop_callbacks(&a->transport);
        UA_Client_disconnect(a->client);
        UA_Client_delete(a->client);
        a->client = NULL;
        memset(&a->transport, 0, sizeof(a->transport));
        return rc;
    }

    a->connected = true;
    return UA_STATUSCODE_GOOD;
}

bool occ_opcua_c0_ready(
    occ_opcua_c0_adapter_t *a
)
{
    return a && a->client && a->connected &&
           fair_opcua_transport_ready(&a->transport);
}

void occ_opcua_c0_stop(
    occ_opcua_c0_adapter_t *a
)
{
    if (!a || !a->client) {
        return;
    }

    fair_opcua_transport_stop_callbacks(&a->transport);
    UA_Client_disconnect(a->client);
    UA_Client_delete(a->client);

    a->client = NULL;
    a->connected = false;
    a->request_in_flight = false;

    memset(&a->request_context, 0, sizeof(a->request_context));
    memset(&a->request_slot, 0, sizeof(a->request_slot));
    memset(&a->request_snapshot, 0, sizeof(a->request_snapshot));
    memset(&a->transport, 0, sizeof(a->transport));
}


UA_StatusCode occ_opcua_c0_send_snapshot(
    occ_opcua_c0_adapter_t *a,
    unsigned int timeout_ms
)
{
    if (!a || !a->client || !a->connected ||
        !fair_opcua_transport_ready(&a->transport) ||
        a->request_in_flight || timeout_ms == 0U) {
        return UA_STATUSCODE_BADINVALIDSTATE;
    }

    fair_v1_payload_t payload;

    if (!occ_telemetry_snapshot(
            &a->request_snapshot,
            &payload,
            a->vehicle_id)) {
        return UA_STATUSCODE_BADINTERNALERROR;
    }


    /* Operational OPC UA: preserve continuous vehicle sequence. */
    memset(&a->request_slot, 0, sizeof(a->request_slot));
    a->request_slot.seq = payload.seq;
    a->request_slot.t_sched_us = payload.t_sched_us;


    /*
     * Set before submission so callback-owned memory
     * is never stored on the caller's stack.
     */
    a->request_in_flight = true;

    /* OCC_OPCUA_VALIDATION_TRACE_V1 */
    ESP_LOGI("OCC_C0_DIAG",
             "pre-submit seq=%lu slot_seq=%lu "
             "sched=%lld slot_sched=%lld "
             "namespace_resolved=%u send_outcome=%u",
             (unsigned long)payload.seq,
             (unsigned long)a->request_slot.seq,
             (long long)payload.t_sched_us,
             (long long)a->request_slot.t_sched_us,
             (unsigned int)a->transport.namespace_resolved,
             (unsigned int)a->request_slot.has_send_outcome);

    UA_StatusCode rc = fair_opcua_transport_submit(
        &a->transport,
        &a->request_slot,
        &payload,
        &a->request_context
    );

    if (rc != UA_STATUSCODE_GOOD) {
        ESP_LOGE("OCC_C0_DIAG",
                 "transport_submit failed status=0x%08lx",
                 (unsigned long)rc);
        /*
         * Immediate submission failure should not
         * schedule a successful async request.
         * Still require a disconnect before retrying.
         */
        return rc;
    }

    const int64_t deadline_us =
        esp_timer_get_time() +
        (int64_t)timeout_ms * 1000;

    while (!a->request_context.response_seen) {
        if (esp_timer_get_time() >= deadline_us) {
            return UA_STATUSCODE_BADTIMEOUT;
        }

        rc = fair_opcua_transport_iterate(
            &a->transport,
            10U
        );

        if (rc != UA_STATUSCODE_GOOD) {
            return rc;
        }
    }

    if (!a->request_context.correlation_ok ||
        !a->request_slot.has_t_ack_rx) {
        return UA_STATUSCODE_BADINTERNALERROR;
    }

    ESP_LOGI("OCC_C0_DIAG", "ack received vehicle=%s seq=%lu",
             a->vehicle_id, (unsigned long)a->request_snapshot.seq);
    a->request_in_flight = false;
    return UA_STATUSCODE_GOOD;
}
