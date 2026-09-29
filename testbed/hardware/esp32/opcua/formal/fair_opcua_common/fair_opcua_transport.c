#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "esp_log.h"
#include "esp_timer.h"

#include "open62541.h"

#include "fair_v1_core.h"
#include "fair_opcua_transport.h"

static const char *TAG =
    "FAIR_OPCUA";

static bool fair_opcua_string_matches(
    const UA_String *value,
    const char *expected
)
{
    if (
        value == NULL ||
        expected == NULL
    ) {
        return false;
    }

    const size_t expected_len =
        strlen(expected);

    return
        value->length ==
            expected_len &&
        (
            expected_len == 0U ||
            memcmp(
                value->data,
                expected,
                expected_len
            ) == 0
        );
}

static void fair_opcua_method_response(
    UA_Client *client,
    void *userdata,
    UA_UInt32 request_id,
    UA_CallResponse *response
)
{
    /*
     * Frozen FAIR-V1 candidate receive boundary:
     * complete async Method response has become
     * application-visible to this callback.
     */
    const int64_t t_ack_rx_us =
        esp_timer_get_time();

    (void)client;

    fair_opcua_request_context_t *ctx =
        (fair_opcua_request_context_t *)
            userdata;

    if (
        ctx == NULL ||
        ctx->transport == NULL ||
        ctx->slot == NULL
    ) {
        return;
    }

    ctx->response_seen =
        true;

    ctx->request_id =
        request_id;

    if (
        !ctx->transport
            ->accept_callbacks
    ) {
        ctx->active =
            false;

        return;
    }

    if (
        response == NULL ||
        response
            ->responseHeader
            .serviceResult !=
                UA_STATUSCODE_GOOD ||
        response->resultsSize != 1U
    ) {
        ctx->active =
            false;

        return;
    }

    const UA_CallMethodResult *result =
        &response->results[0];

    if (
        result->statusCode !=
            UA_STATUSCODE_GOOD ||
        result->outputArgumentsSize !=
            2U
    ) {
        ctx->active =
            false;

        return;
    }

    const UA_Variant *serial_variant =
        &result->outputArguments[0];

    const UA_Variant *seq_variant =
        &result->outputArguments[1];

    if (
        !UA_Variant_hasScalarType(
            serial_variant,
            &UA_TYPES[UA_TYPES_STRING]
        ) ||
        !UA_Variant_hasScalarType(
            seq_variant,
            &UA_TYPES[UA_TYPES_UINT32]
        )
    ) {
        ctx->active =
            false;

        return;
    }

    const UA_String *received_serial =
        (const UA_String *)
            serial_variant->data;

    const UA_UInt32 received_seq =
        *(const UA_UInt32 *)
            seq_variant->data;

    if (
        !fair_opcua_string_matches(
            received_serial,
            ctx->expected_serial_number
        ) ||
        received_seq !=
            ctx->expected_seq
    ) {
        ctx->active =
            false;

        return;
    }

    ctx->correlation_ok =
        fair_v1_slot_mark_echo_received(
            ctx->slot,
            t_ack_rx_us
        );

    ctx->active =
        false;
}

bool fair_opcua_transport_init(
    fair_opcua_transport_t *transport,
    UA_Client *client,
    const char *endpoint,
    const char *serial_number
)
{
    if (
        transport == NULL ||
        client == NULL ||
        endpoint == NULL ||
        endpoint[0] == '\0' ||
        serial_number == NULL ||
        serial_number[0] == '\0'
    ) {
        return false;
    }

    memset(
        transport,
        0,
        sizeof(*transport)
    );

    transport->client =
        client;

    transport->endpoint =
        endpoint;

    transport->serial_number =
        serial_number;

    transport->accept_callbacks =
        true;

    return true;
}

bool fair_opcua_transport_ready(
    fair_opcua_transport_t *transport
)
{
    if (
        transport == NULL ||
        transport->client == NULL
    ) {
        return false;
    }

    UA_SecureChannelState channel_state;
    UA_SessionState session_state;
    UA_StatusCode connect_status;

    UA_Client_getState(
        transport->client,
        &channel_state,
        &session_state,
        &connect_status
    );

    return
        connect_status ==
            UA_STATUSCODE_GOOD &&
        session_state ==
            UA_SESSIONSTATE_ACTIVATED;
}

static UA_StatusCode
fair_opcua_resolve_namespace(
    fair_opcua_transport_t *transport
)
{
    UA_String namespace_uri =
        UA_STRING(
            FAIR_OPCUA_NAMESPACE_URI
        );

    UA_UInt16 index = 0U;

    const UA_StatusCode rc =
        UA_Client_getNamespaceIndex(
            transport->client,
            namespace_uri,
            &index
        );

    if (
        rc == UA_STATUSCODE_GOOD
    ) {
        transport->namespace_index =
            index;

        transport->namespace_resolved =
            true;
    } else {
        transport->namespace_resolved =
            false;
    }

    return rc;
}

UA_StatusCode fair_opcua_transport_connect(
    fair_opcua_transport_t *transport
)
{
    if (
        transport == NULL ||
        transport->client == NULL
    ) {
        return
            UA_STATUSCODE_BADINVALIDARGUMENT;
    }

    transport->namespace_resolved =
        false;

    const UA_StatusCode rc =
        UA_Client_connect(
            transport->client,
            transport->endpoint
        );

    if (
        rc != UA_STATUSCODE_GOOD
    ) {
        return rc;
    }

    return
        fair_opcua_resolve_namespace(
            transport
        );
}

UA_StatusCode fair_opcua_transport_reconnect(
    fair_opcua_transport_t *transport
)
{
    return
        fair_opcua_transport_connect(
            transport
        );
}

UA_StatusCode fair_opcua_transport_iterate(
    fair_opcua_transport_t *transport,
    UA_UInt32 timeout_ms
)
{
    if (
        transport == NULL ||
        transport->client == NULL
    ) {
        return
            UA_STATUSCODE_BADINVALIDARGUMENT;
    }

    return
        UA_Client_run_iterate(
            transport->client,
            timeout_ms
        );
}

UA_StatusCode fair_opcua_transport_submit(
    fair_opcua_transport_t *transport,
    fair_v1_slot_t *slot,
    const fair_v1_payload_t *payload,
    fair_opcua_request_context_t *ctx
)
{
    if (
        transport == NULL ||
        transport->client == NULL ||
        slot == NULL ||
        payload == NULL ||
        ctx == NULL ||
        !transport->namespace_resolved ||
        slot->has_send_outcome ||
        !fair_v1_payload_matches_slot(
            payload,
            slot
        )
    ) {
        return
            UA_STATUSCODE_BADINVALIDARGUMENT;
    }

    memset(
        ctx,
        0,
        sizeof(*ctx)
    );

    ctx->transport =
        transport;

    ctx->slot =
        slot;

    ctx->expected_serial_number =
        payload->serialNumber;

    ctx->expected_seq =
        payload->seq;

    UA_String schema_ver =
        UA_STRING(
            (char *)payload->schema_ver
        );

    UA_String serial_number =
        UA_STRING(
            (char *)payload->serialNumber
        );

    UA_UInt32 seq =
        (UA_UInt32)payload->seq;

    UA_Int64 t_sched_us =
        (UA_Int64)payload->t_sched_us;

    UA_Float speed =
        (UA_Float)payload->speed;

    UA_Float pos_x =
        (UA_Float)payload->pos_x;

    UA_Float pos_y =
        (UA_Float)payload->pos_y;

    UA_Float heading =
        (UA_Float)payload->heading;

    UA_Float battery_pct =
        (UA_Float)payload->battery_pct;

    UA_String state =
        UA_STRING(
            (char *)payload->state
        );

    UA_Variant inputs[10];

    for (
        size_t i = 0U;
        i < 10U;
        ++i
    ) {
        UA_Variant_init(
            &inputs[i]
        );
    }

    UA_Variant_setScalar(
        &inputs[0],
        &schema_ver,
        &UA_TYPES[UA_TYPES_STRING]
    );

    UA_Variant_setScalar(
        &inputs[1],
        &serial_number,
        &UA_TYPES[UA_TYPES_STRING]
    );

    UA_Variant_setScalar(
        &inputs[2],
        &seq,
        &UA_TYPES[UA_TYPES_UINT32]
    );

    UA_Variant_setScalar(
        &inputs[3],
        &t_sched_us,
        &UA_TYPES[UA_TYPES_INT64]
    );

    UA_Variant_setScalar(
        &inputs[4],
        &speed,
        &UA_TYPES[UA_TYPES_FLOAT]
    );

    UA_Variant_setScalar(
        &inputs[5],
        &pos_x,
        &UA_TYPES[UA_TYPES_FLOAT]
    );

    UA_Variant_setScalar(
        &inputs[6],
        &pos_y,
        &UA_TYPES[UA_TYPES_FLOAT]
    );

    UA_Variant_setScalar(
        &inputs[7],
        &heading,
        &UA_TYPES[UA_TYPES_FLOAT]
    );

    UA_Variant_setScalar(
        &inputs[8],
        &battery_pct,
        &UA_TYPES[UA_TYPES_FLOAT]
    );

    UA_Variant_setScalar(
        &inputs[9],
        &state,
        &UA_TYPES[UA_TYPES_STRING]
    );

    const UA_NodeId object_id =
        UA_NODEID_STRING(
            transport->namespace_index,
            FAIR_OPCUA_OBJECT_NODEID
        );

    const UA_NodeId method_id =
        UA_NODEID_STRING(
            transport->namespace_index,
            FAIR_OPCUA_METHOD_NODEID
        );

    /*
     * Frozen FAIR-V1 send boundary:
     * immediately before asynchronous
     * OPC UA Method-call submission.
     */
    const int64_t t_send_us =
        esp_timer_get_time();

    UA_UInt32 request_id = 0U;

    const UA_StatusCode rc =
        UA_Client_call_async(
            transport->client,
            object_id,
            method_id,
            10U,
            inputs,
            fair_opcua_method_response,
            ctx,
            &request_id
        );

    ctx->request_id =
        request_id;

    ctx->submit_status =
        rc;

    ctx->active =
        rc ==
        UA_STATUSCODE_GOOD;

    const bool submission_success =
        rc ==
        UA_STATUSCODE_GOOD;

    if (
        !fair_v1_slot_mark_send_result(
            slot,
            t_send_us,
            submission_success
        )
    ) {
        ESP_LOGE(
            TAG,
            "slot send-result update failed"
        );

        return
            UA_STATUSCODE_BADINTERNALERROR;
    }

    return rc;
}

void fair_opcua_transport_stop_callbacks(
    fair_opcua_transport_t *transport
)
{
    if (
        transport != NULL
    ) {
        transport->accept_callbacks =
            false;
    }
}
