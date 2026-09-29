cmake_minimum_required(VERSION 3.16)

set(
    EXTRA_COMPONENT_DIRS
    "../../../../fair_v1_core"
    "../../fair_mqtt_common"
)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)

project(fair_v1_mqtt_c0_vehicle1)
