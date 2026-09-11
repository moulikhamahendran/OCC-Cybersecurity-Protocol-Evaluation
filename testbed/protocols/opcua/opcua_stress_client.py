import argparse
import asyncio
import os
import time
from pathlib import Path

from asyncua import Client, ua
from asyncua.crypto.security_policies import (
    SecurityPolicyBasic256Sha256,
)


TESTBED_DIR = Path(__file__).resolve().parents[2]
CERT_DIR = TESTBED_DIR / "config" / "opcua" / "certs"

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

PASSWORD = os.getenv(
    "OPCUA_PASSWORD",
)

PORTS = {
    "C0": 4840,
    "C1": 4841,
    "C2": 4842,
}


async def configure_client(client):
    client.application_uri = CLIENT_URI

    if SECURITY_LEVEL == "C0":
        return

    if PASSWORD is None:
        raise RuntimeError(
            f"OPCUA_PASSWORD must be set for {SECURITY_LEVEL}"
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


async def get_reading(client):
    ns = await client.get_namespace_index(
        NAMESPACE_URI
    )

    return await client.nodes.objects.get_child(
        [
            f"{ns}:Vehicle",
            f"{ns}:Reading",
        ]
    )


async def connection_worker(deadline, stats):
    endpoint = (
        f"opc.tcp://127.0.0.1:"
        f"{PORTS[SECURITY_LEVEL]}/occ/"
    )

    while time.monotonic() < deadline:
        client = Client(
            url=endpoint,
            timeout=3,
        )

        try:
            await configure_client(client)
            await client.connect()

            stats["success"] += 1

        except Exception:
            stats["failure"] += 1

        finally:
            try:
                await client.disconnect()
            except Exception:
                pass


async def read_worker(deadline, stats):
    endpoint = (
        f"opc.tcp://127.0.0.1:"
        f"{PORTS[SECURITY_LEVEL]}/occ/"
    )

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
                stats["success"] += 1
            except Exception:
                stats["failure"] += 1

    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


class Handler:
    def datachange_notification(
        self,
        node,
        value,
        data,
    ):
        pass


async def subscription_worker(
    deadline,
    stats,
    subscriptions_per_client,
):
    endpoint = (
        f"opc.tcp://127.0.0.1:"
        f"{PORTS[SECURITY_LEVEL]}/occ/"
    )

    client = Client(
        url=endpoint,
        timeout=3,
    )

    await configure_client(client)

    subscriptions = []

    try:
        await client.connect()
        reading = await get_reading(client)

        for _ in range(
            subscriptions_per_client
        ):
            try:
                sub = await client.create_subscription(
                    50,
                    Handler(),
                )

                await sub.subscribe_data_change(
                    reading
                )

                subscriptions.append(sub)
                stats["success"] += 1

            except Exception:
                stats["failure"] += 1

        remaining = (
            deadline
            - time.monotonic()
        )

        if remaining > 0:
            await asyncio.sleep(
                remaining
            )

    finally:
        for sub in subscriptions:
            try:
                await sub.delete()
            except Exception:
                pass

        try:
            await client.disconnect()
        except Exception:
            pass


async def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--attack",
        required=True,
        choices=[
            "connection",
            "read",
            "subscription",
        ],
    )

    parser.add_argument(
        "--duration",
        type=float,
        default=5,
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--subscriptions-per-client",
        type=int,
        default=5,
    )

    args = parser.parse_args()

    if not 1 <= args.workers <= 20:
        raise ValueError(
            "workers must be between 1 and 20"
        )

    if not 1 <= args.subscriptions_per_client <= 10:
        raise ValueError(
            "subscriptions-per-client must be between 1 and 10"
        )

    if args.duration <= 0 or args.duration > 90:
        raise ValueError(
            "duration must be > 0 and <= 90 seconds"
        )

    stats = {
        "success": 0,
        "failure": 0,
    }

    deadline = (
        time.monotonic()
        + args.duration
    )

    start = time.perf_counter()

    if args.attack == "connection":
        tasks = [
            connection_worker(
                deadline,
                stats,
            )
            for _ in range(
                args.workers
            )
        ]

    elif args.attack == "read":
        tasks = [
            read_worker(
                deadline,
                stats,
            )
            for _ in range(
                args.workers
            )
        ]

    else:
        tasks = [
            subscription_worker(
                deadline,
                stats,
                args.subscriptions_per_client,
            )
            for _ in range(
                args.workers
            )
        ]

    await asyncio.gather(
        *tasks,
        return_exceptions=True,
    )

    elapsed = (
        time.perf_counter()
        - start
    )

    total = (
        stats["success"]
        + stats["failure"]
    )

    print()
    print("OPC UA CONTROLLED STRESS TEST")
    print("Security level :", SECURITY_LEVEL)
    print("Attack type    :", args.attack)
    print("Workers        :", args.workers)
    print("Duration       :", round(elapsed, 3), "s")
    print("Successful ops :", stats["success"])
    print("Failed ops     :", stats["failure"])
    print("Total ops      :", total)

    if elapsed > 0:
        print(
            "Operations/sec :",
            round(
                total / elapsed,
                2,
            ),
        )

    print()


if __name__ == "__main__":
    asyncio.run(main())
