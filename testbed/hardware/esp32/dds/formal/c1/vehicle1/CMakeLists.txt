cmake_minimum_required(VERSION 3.16)
set(EXTRA_COMPONENT_DIRS
    "../../../../fair_v1_core"
    "../../fair_dds_types"
    "../../fair_dds_common"
    "../../.deps/microcdr"
    "../../.deps/microxrcedds"
)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(fair_v1_dds_c1_vehicle1)
