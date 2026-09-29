#!/usr/bin/env python3

import argparse
import asyncio
from collections import deque
import json
import os
from pathlib import Path
import time
import uuid

from asyncua import Server, ua
from asyncua.common.methods import uamethod
from asyncua.crypto.permission_rules import (
    User,
    UserRole,
)


NAMESPACE_URI = "urn:fair-v1:opcua"

OBJECT_NODEID = (
    "FAIR.V1.VehicleService"
)

METHOD_NODEID = (
    "FAIR.V1.SubmitTelemetry"
)

DATASET_SCHEMA_VERSION = "1.0"
PAYLOAD_SCHEMA_VERSION = "0.1"


def _now_us():
    return (
        time.monotonic_ns()
        // 1000
    )


class OCCUserManager:

    def get_user(
        self,
        iserver,
        username=None,
        password=None,
        certificate=None,
    ):
        del iserver
        del certificate

        expected_user = (
            os.getenv(
                "OPCUA_USERNAME",
                "occuser",
            )
        )

        expected_password = (
            os.getenv(
                "OPCUA_PASSWORD"
            )
        )

        if (
            expected_password
            and username
            == expected_user
            and password
            == expected_password
        ):
            return User(
                role=UserRole.User
            )

        return None


class EventLogger:

    def __init__(
        self,
        path,
    ):
        self.path = Path(path)

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.file = self.path.open(
            "x",
            encoding="utf-8",
            buffering=1,
        )

        self.pending = deque()

    def enqueue(
        self,
        event,
    ):
        self.pending.append(
            event
        )

    def flush_pending(
        self,
    ):
        while self.pending:
            event = (
                self.pending.popleft()
            )

            self.file.write(
                json.dumps(
                    event,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n"
            )

        self.file.flush()

    async def flush_loop(
        self,
    ):
        while True:
            self.flush_pending()
            await asyncio.sleep(0.01)

    def close(
        self,
    ):
        self.flush_pending()
        self.file.close()


class FairOpcuaService:

    def __init__(
        self,
        *,
        run_id,
        clock_domain,
        service_id,
        event_logger,
    ):
        self.run_id = run_id
        self.clock_domain = (
            clock_domain
        )
        self.service_id = service_id
        self.event_logger = (
            event_logger
        )

    def _event(
        self,
        *,
        serial_number,
        seq,
        event_type,
        event_time_us,
    ):
        return {
            "event_id":
                str(uuid.uuid4()),

            "run_id":
                self.run_id,

            "serialNumber":
                serial_number,

            "seq":
                seq,

            "protocol":
                "opcua",

            "event_type":
                event_type,

            "event_time_us":
                event_time_us,

            "clock_domain":
                self.clock_domain,

            "service_id":
                self.service_id,

            "protocol_correlation": {
                "object_node_id":
                    OBJECT_NODEID,

                "method_node_id":
                    METHOD_NODEID,
            },

            "dataset_schema_version":
                DATASET_SCHEMA_VERSION,

            "event_source_layer":
                "fair_echo_application",
        }

    async def handle_submit(
        self,
        *,
        t_occ_rx_us,
        schema_ver,
        serial_number,
        seq,
        t_sched_us,
        speed,
        pos_x,
        pos_y,
        heading,
        battery_pct,
        state,
    ):
        if (
            schema_ver
            != PAYLOAD_SCHEMA_VERSION
        ):
            raise ValueError(
                "schema_ver mismatch"
            )

        if (
            not isinstance(
                serial_number,
                str,
            )
            or not serial_number
        ):
            raise ValueError(
                "serialNumber invalid"
            )

        if (
            isinstance(seq, bool)
            or not isinstance(seq, int)
            or seq < 0
            or seq > 599
        ):
            raise ValueError(
                "seq invalid"
            )

        if (
            isinstance(
                t_sched_us,
                bool,
            )
            or not isinstance(
                t_sched_us,
                int,
            )
        ):
            raise ValueError(
                "t_sched_us invalid"
            )

        for value in (
            speed,
            pos_x,
            pos_y,
            heading,
            battery_pct,
        ):
            if (
                isinstance(value, bool)
                or not isinstance(
                    value,
                    (int, float),
                )
            ):
                raise ValueError(
                    "float telemetry invalid"
                )

        if not isinstance(
            state,
            str,
        ):
            raise ValueError(
                "state invalid"
            )

        self.event_logger.enqueue(
            self._event(
                serial_number=
                    serial_number,

                seq=
                    seq,

                event_type=
                    "occ_rx",

                event_time_us=
                    t_occ_rx_us,
            )
        )

        # The application response contains
        # exactly serialNumber + seq.

        t_occ_tx_us = _now_us()

        self.event_logger.enqueue(
            self._event(
                serial_number=
                    serial_number,

                seq=
                    seq,

                event_type=
                    "occ_tx",

                event_time_us=
                    t_occ_tx_us,
            )
        )

        return (
            serial_number,
            seq,
        )


def make_submit_callback(
    service,
):

    @uamethod
    async def submit_telemetry(
        parent,
        schema_ver,
        serial_number,
        seq,
        t_sched_us,
        speed,
        pos_x,
        pos_y,
        heading,
        battery_pct,
        state,
    ):
        t_occ_rx_us = _now_us()

        del parent

        return await service.handle_submit(
            t_occ_rx_us=
                t_occ_rx_us,

            schema_ver=
                schema_ver,

            serial_number=
                serial_number,

            seq=
                seq,

            t_sched_us=
                t_sched_us,

            speed=
                speed,

            pos_x=
                pos_x,

            pos_y=
                pos_y,

            heading=
                heading,

            battery_pct=
                battery_pct,

            state=
                state,
        )

    return submit_telemetry


async def add_fair_method(
    server,
    service,
):
    idx = await (
        server.register_namespace(
            NAMESPACE_URI
        )
    )

    obj = await (
        server.nodes.objects.add_object(
            ua.NodeId(
                OBJECT_NODEID,
                idx,
            ),
            "FAIR_V1_VehicleService",
        )
    )

    method = await obj.add_method(
        ua.NodeId(
            METHOD_NODEID,
            idx,
        ),
        "SubmitTelemetry",
        make_submit_callback(
            service
        ),
        [
            ua.VariantType.String,
            ua.VariantType.String,
            ua.VariantType.UInt32,
            ua.VariantType.Int64,
            ua.VariantType.Float,
            ua.VariantType.Float,
            ua.VariantType.Float,
            ua.VariantType.Float,
            ua.VariantType.Float,
            ua.VariantType.String,
        ],
        [
            ua.VariantType.String,
            ua.VariantType.UInt32,
        ],
    )

    return idx, obj, method


def parse_args():
    p = argparse.ArgumentParser()

    p.add_argument(
        "--profile",
        choices=(
            "C0",
            "C1",
            "C2",
        ),
        required=True,
    )

    p.add_argument(
        "--endpoint",
        required=True,
    )

    p.add_argument(
        "--certificate",
    )

    p.add_argument(
        "--private-key",
    )

    p.add_argument(
        "--run-id",
        required=True,
    )

    p.add_argument(
        "--clock-domain",
        required=True,
    )

    p.add_argument(
        "--service-id",
        required=True,
    )

    p.add_argument(
        "--event-log",
        required=True,
    )

    return p.parse_args()


async def main():
    args = parse_args()

    if args.profile == "C0":
        server = Server()
    else:
        if (
            not args.certificate
            or not args.private_key
        ):
            raise SystemExit(
                "secure profile requires "
                "--certificate and "
                "--private-key"
            )

        if not os.getenv(
            "OPCUA_PASSWORD"
        ):
            raise SystemExit(
                "secure profile requires "
                "OPCUA_PASSWORD"
            )

        server = Server(
            user_manager=
                OCCUserManager()
        )

    await server.init()

    server.set_endpoint(
        args.endpoint
    )

    server.set_server_name(
        "FAIR-V1 Formal OPC UA OCC"
    )

    if args.profile == "C0":
        server.set_security_policy(
            [
                ua.SecurityPolicyType
                .NoSecurity
            ]
        )

    else:
        server.set_identity_tokens(
            [
                ua.UserNameIdentityToken
            ]
        )

        await server.set_application_uri(
            "urn:ovgu:occ:opcua:c1:server"
        )

        await server.load_certificate(
            args.certificate
        )

        await server.load_private_key(
            args.private_key
        )

        if args.profile == "C1":
            server.set_security_policy(
                [
                    ua.SecurityPolicyType
                    .Basic256Sha256_Sign
                ]
            )

        else:
            server.set_security_policy(
                [
                    ua.SecurityPolicyType
                    .Basic256Sha256_SignAndEncrypt
                ]
            )

    event_logger = EventLogger(
        args.event_log
    )

    service = FairOpcuaService(
        run_id=
            args.run_id,

        clock_domain=
            args.clock_domain,

        service_id=
            args.service_id,

        event_logger=
            event_logger,
    )

    idx, obj, method = (
        await add_fair_method(
            server,
            service,
        )
    )

    print(
        "FAIR-V1 OPC UA formal service"
    )

    print(
        "profile=",
        args.profile,
    )

    print(
        "namespace_index=",
        idx,
    )

    print(
        "object_node=",
        obj.nodeid,
    )

    print(
        "method_node=",
        method.nodeid,
    )

    flush_task = (
        asyncio.create_task(
            event_logger.flush_loop()
        )
    )

    try:
        async with server:
            while True:
                await asyncio.sleep(1)

    finally:
        flush_task.cancel()

        try:
            await flush_task
        except asyncio.CancelledError:
            pass

        event_logger.close()


if __name__ == "__main__":
    asyncio.run(main())
