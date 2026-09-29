#pragma once

#include "open62541.h"

#define FAIR_OPCUA_PROFILE_NAME "C0"
#define FAIR_OPCUA_PROFILE_SECURE 0
#define FAIR_OPCUA_PROFILE_SIGN_AND_ENCRYPT 0

UA_Client *fair_opcua_profile_create_client(
    void
);
