#pragma once

#include <stdbool.h>
#include "open62541.h"
#include "fair_opcua_transport.h"
#include "vehicle_state.h"
#include "protocol_selection.h"

typedef struct {
    UA_Client *client;
    fair_opcua_transport_t transport;
    char endpoint[256];
    char vehicle_id[64];
    occ_security_t security;
    bool connected;
    bool request_in_flight;
    fair_v1_slot_t request_slot;
    fair_opcua_request_context_t request_context;
    vehicle_state_t request_snapshot;
} occ_opcua_c0_adapter_t;

bool occ_opcua_profile_init(
    occ_opcua_c0_adapter_t *adapter,
    const char *endpoint,
    const char *vehicle_id,
    occ_security_t security
);

bool occ_opcua_c0_init(
    occ_opcua_c0_adapter_t *adapter,
    const char *endpoint,
    const char *vehicle_id
);

UA_StatusCode occ_opcua_c0_start(
    occ_opcua_c0_adapter_t *adapter
);

bool occ_opcua_c0_ready(
    occ_opcua_c0_adapter_t *adapter
);

void occ_opcua_c0_stop(
    occ_opcua_c0_adapter_t *adapter
);

/*
 * Single outstanding request.
 * On timeout, stop/disconnect before attempting another send.
 * Call from the protocol-owning task only.
 */
UA_StatusCode occ_opcua_c0_send_snapshot(
    occ_opcua_c0_adapter_t *adapter,
    unsigned int timeout_ms
);
