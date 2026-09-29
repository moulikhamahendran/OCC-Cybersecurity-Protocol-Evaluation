#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "open62541.h"

#include "fair_v1_core.h"

#ifdef __cplusplus
extern "C" {
#endif

#define FAIR_OPCUA_NAMESPACE_URI \
    "urn:fair-v1:opcua"

#define FAIR_OPCUA_OBJECT_NODEID \
    "FAIR.V1.VehicleService"

#define FAIR_OPCUA_METHOD_NODEID \
    "FAIR.V1.SubmitTelemetry"

typedef struct fair_opcua_transport
    fair_opcua_transport_t;

typedef struct {
    fair_opcua_transport_t *transport;

    fair_v1_slot_t *slot;

    const char *expected_serial_number;

    uint32_t expected_seq;

    UA_UInt32 request_id;

    UA_StatusCode submit_status;

    bool active;
    bool response_seen;
    bool correlation_ok;
} fair_opcua_request_context_t;

struct fair_opcua_transport {
    UA_Client *client;

    const char *endpoint;
    const char *serial_number;

    UA_UInt16 namespace_index;

    bool namespace_resolved;
    bool accept_callbacks;
};

bool fair_opcua_transport_init(
    fair_opcua_transport_t *transport,
    UA_Client *client,
    const char *endpoint,
    const char *serial_number
);

bool fair_opcua_transport_ready(
    fair_opcua_transport_t *transport
);

UA_StatusCode fair_opcua_transport_connect(
    fair_opcua_transport_t *transport
);

UA_StatusCode fair_opcua_transport_reconnect(
    fair_opcua_transport_t *transport
);

UA_StatusCode fair_opcua_transport_iterate(
    fair_opcua_transport_t *transport,
    UA_UInt32 timeout_ms
);

UA_StatusCode fair_opcua_transport_submit(
    fair_opcua_transport_t *transport,
    fair_v1_slot_t *slot,
    const fair_v1_payload_t *payload,
    fair_opcua_request_context_t *request_context
);

void fair_opcua_transport_stop_callbacks(
    fair_opcua_transport_t *transport
);

#ifdef __cplusplus
}
#endif
