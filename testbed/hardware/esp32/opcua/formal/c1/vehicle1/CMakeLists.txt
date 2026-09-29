cmake_minimum_required(VERSION 3.16)

set(
    EXTRA_COMPONENT_DIRS
    "../../../../fair_v1_core"
    "../../fair_opcua_common"
    "../../../c1/components/open62541lib"
)

set(
    SDKCONFIG_DEFAULTS
    "${CMAKE_CURRENT_LIST_DIR}/../../../c1/sdkconfig.defaults"
)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)

project(fair_v1_opcua_c1_vehicle1)
