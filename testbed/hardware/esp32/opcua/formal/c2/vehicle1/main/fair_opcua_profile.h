#pragma once

#include "open62541.h"

#define FAIR_OPCUA_PROFILE_NAME "C2"
#define FAIR_OPCUA_PROFILE_SECURE 1
#define FAIR_OPCUA_PROFILE_SIGN_AND_ENCRYPT 1

UA_Client *fair_opcua_profile_create_client(
    void
);
