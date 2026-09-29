#!/usr/bin/env python3

import asyncio
import json
from pathlib import Path
import tempfile

from asyncua import Server, ua
from jsonschema import (
    Draft202012Validator,
)

import fair_opcua_server as appmod


HERE = Path(__file__).resolve().parent

REPO = HERE

while (
    REPO != REPO.parent
    and not (
        REPO
        / "testbed"
        / "docs"
        / "fair_v1"
        / "schemas"
    ).exists()
):
    REPO = REPO.parent


OCC_SCHEMA = json.loads(
    (
        REPO
        / "testbed"
        / "docs"
        / "fair_v1"
        / "schemas"
        / "fair_v1_occ_message_event.schema.json"
    ).read_text()
)


async def test_service(
    tmp,
):
    log_path = (
        tmp /
        "opcua_events.jsonl"
    )

    logger = appmod.EventLogger(
        log_path
    )

    service = appmod.FairOpcuaService(
        run_id="TEST-OPCUA-001",
        clock_domain=
            "test_monotonic",

        service_id=
            "test-opcua-service",

        event_logger=
            logger,
    )

    original_now = appmod._now_us

    appmod._now_us = (
        lambda: 1000200
    )

    try:
        result = await (
            service.handle_submit(
                t_occ_rx_us=
                    1000000,

                schema_ver=
                    "0.1",

                serial_number=
                    "VM-001",

                seq=
                    123,

                t_sched_us=
                    12300000,

                speed=
                    1.0,

                pos_x=
                    2.0,

                pos_y=
                    3.0,

                heading=
                    4.0,

                battery_pct=
                    80.0,

                state=
                    "RUNNING",
            )
        )

    finally:
        appmod._now_us = (
            original_now
        )

    assert result == (
        "VM-001",
        123,
    )

    logger.flush_pending()
    logger.close()

    events = [
        json.loads(line)
        for line in
        log_path.read_text()
        .splitlines()
    ]

    assert len(events) == 2

    for event in events:
        Draft202012Validator(
            OCC_SCHEMA
        ).validate(event)

    assert (
        events[0]["event_type"]
        == "occ_rx"
    )

    assert (
        events[0]["event_time_us"]
        == 1000000
    )

    assert (
        events[1]["event_type"]
        == "occ_tx"
    )

    assert (
        events[1]["event_time_us"]
        == 1000200
    )


async def test_method_model(
    tmp,
):
    log_path = (
        tmp /
        "model_events.jsonl"
    )

    logger = appmod.EventLogger(
        log_path
    )

    service = appmod.FairOpcuaService(
        run_id="TEST-OPCUA-002",
        clock_domain=
            "test_monotonic",

        service_id=
            "test-opcua-service",

        event_logger=
            logger,
    )

    server = Server()

    await server.init()

    server.set_security_policy(
        [
            ua.SecurityPolicyType
            .NoSecurity
        ]
    )

    idx, obj, method = (
        await appmod.add_fair_method(
            server,
            service,
        )
    )

    assert idx > 0

    assert (
        obj.nodeid.Identifier
        == appmod.OBJECT_NODEID
    )

    assert (
        method.nodeid.Identifier
        == appmod.METHOD_NODEID
    )

    methods = await (
        obj.get_methods()
    )

    assert any(
        m.nodeid.Identifier
        == appmod.METHOD_NODEID
        for m in methods
    )

    logger.close()


async def main():
    Draft202012Validator.check_schema(
        OCC_SCHEMA
    )

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)

        await test_service(tmp)
        await test_method_model(tmp)

    print(
        "FAIR_V1_PI_OPCUA_METHOD_TEST: PASS"
    )

    print(
        "OCC_EVENT_SCHEMA_VALIDATION: PASS"
    )

    print(
        "OPCUA_METHOD_MODEL_TEST: PASS"
    )


if __name__ == "__main__":
    asyncio.run(main())
