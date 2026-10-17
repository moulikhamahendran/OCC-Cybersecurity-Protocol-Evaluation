#pragma once
#include "open62541.h"
#include "protocol_selection.h"
/* C0 remains the existing FAIR-V1 profile; C1/C2 reuse its transport. */
UA_Client *occ_opcua_profile_create_client(occ_security_t security);
