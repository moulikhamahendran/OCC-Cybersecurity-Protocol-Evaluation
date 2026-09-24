#!/usr/bin/env python3

"""Controlled OPC UA authorized read-service availability flood.

Threat model:
A compromised but authorized OPC UA client generates sustained read-service
pressure through the normal protocol path.

The client uses the same C0/C1/C2 security configuration as the validated
OPC UA benchmark/stress implementation.
"""

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

from asyncua import Client, ua
from asyncua.crypto.security_policies import (
    SecurityPolicyBasic256Sha256,
)


TESTBED_DIR = Path(__file__).resolve().parents[1]

CERT_DIR = (
    TESTBED_DIR
    / "config"
    / "opcua"
    / "certs"
)

SERVER_CERT = CERT_DIR / "server_cert.der"
CLIENT_CERT = CERT_DIR / "client_cert.der"
CLIENT_KEY = CERT_DIR / "client_key.pem"

CLIENT_URI = "urn:ovgu:occ-testbed:opcua:client"
NAMESPACE_URI = "urn:ovgu:occ-testbed:vehicle"

SECURITY_LEVEL = os.getenv(
    "OPCUA_SECURITY_LEVEL",
    "C0",
).upper()

USERNAME = os.getenv(
    "OPCUA_USERNAME",
    "occuser",
)

PASSWORD = os.getenv("OPCUA_PASSWORD")

PORTS = {
    "C0": 4840,
    "C1": 4841,
    "C2": 4842,
}


async def configure_client(
    client: Client,
) -> None:
    client.application_uri = CLIENT_URI

    if SECURITY_LEVEL == "C0":
        return

    if PASSWORD is None:
        raise RuntimeError(
            f"OPCUA_PASSWORD must be set "
            f"for {SECURITY_LEVEL}"
        )

    mode = (
        ua.MessageSecurityMode.Sign
        if SECURITY_LEVEL == "C1"
        else ua.MessageSecurityMode.SignAndEncrypt
    )

    await client.set_security(
        SecurityPolicyBasic256Sha256,
        certificate=str(CLIENT_CERT),
        private_key=str(CLIENT_KEY),
        server_certificate=str(SERVER_CERT),
        mode=mode,
    )

    client.set_user(USERNAME)
    client.set_password(PASSWORD)


async def get_reading(
    client: Client,
):
    namespace_index = (
        await client.get_namespace_index(
            NAMESPACE_URI
        )
    )

    return (
        await client.nodes.objects.get_child(
            [
                f"{namespace_index}:Vehicle",
                f"{namespace_index}:Reading",
            ]
        )
    )


async def read_worker(
    *,
    endpoint: str,
    deadline: float,
    stats: dict[str, int],
) -> None:
    client = Client(
        url=endpoint,
        timeout=3,
    )

    await configure_client(client)

    try:
        await client.connect()

        reading = await get_reading(client)

        while time.monotonic() < deadline:
            try:
                await reading.read_value()
                stats["successful_ops"] += 1
            except Exception:
                stats["failed_ops"] += 1

    except Exception:
        stats["worker_failures"] += 1
        raise

    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


async def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--duration",
        type=float,
        default=30.0,
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=5,
    )

    args = parser.parse_args()

    if args.duration <= 0:
        raise ValueError(
            "duration must be > 0"
        )

    if not 1 <= args.workers <= 20:
        raise ValueError(
            "workers must be between 1 and 20"
        )

    if SECURITY_LEVEL not in PORTS:
        raise ValueError(
            f"Unknown security level: "
            f"{SECURITY_LEVEL}"
        )

    endpoint = os.getenv(
        "OPCUA_ENDPOINT",
        (
            "opc.tcp://127.0.0.1:"
            f"{PORTS[SECURITY_LEVEL]}/occ/"
        ),
    )

    stats = {
        "successful_ops": 0,
        "failed_ops": 0,
        "worker_failures": 0,
    }

    started = time.monotonic()
    deadline = started + args.duration

    results = await asyncio.gather(
        *[
            read_worker(
                endpoint=endpoint,
                deadline=deadline,
                stats=stats,
            )
            for _ in range(args.workers)
        ],
        return_exceptions=True,
    )

    elapsed = (
        time.monotonic()
        - started
    )

    task_errors = sum(
        1
        for result in results
        if isinstance(
            result,
            BaseException,
        )
    )

    total_ops = (
        stats["successful_ops"]
        + stats["failed_ops"]
    )

    operations_per_second = (
        total_ops / elapsed
        if elapsed > 0
        else 0.0
    )

    output = {
        "security_level": SECURITY_LEVEL,
        "endpoint": endpoint,
        "workers": args.workers,
        "duration_target_s": args.duration,
        "elapsed_s": round(
            elapsed,
            6,
        ),
        "successful_ops": (
            stats["successful_ops"]
        ),
        "failed_ops": (
            stats["failed_ops"]
        ),
        "total_ops": total_ops,
        "operations_per_second": round(
            operations_per_second,
            6,
        ),
        "worker_failures": (
            stats["worker_failures"]
        ),
        "task_errors": task_errors,
    }

    print(
        json.dumps(output),
        flush=True,
    )

    if task_errors:
        raise RuntimeError(
            f"{task_errors} OPC UA "
            "read-flood worker(s) failed"
        )


if __name__ == "__main__":
    asyncio.run(main())
